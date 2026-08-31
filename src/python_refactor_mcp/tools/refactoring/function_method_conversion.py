"""Convert a free function to an instance method and back.

Both refactorings deliberately accept a narrow semantics-preserving shape. The
definition and every semantic reference must live in one module, every use must
be a direct call, and the containing class must be plain and undecorated. This
lets the tools rewrite the definition and all callers as one guarded whole-file
edit instead of leaving a partially converted project.
"""

from __future__ import annotations

import os
import symtable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import libcst as cst
from libcst.metadata import CodeRange, MetadataWrapper, PositionProvider

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import RefactorResult
from python_refactor_mcp.tools.analysis.references import find_references
from python_refactor_mcp.util.cst_apply import (
    CstSourceSnapshot,
    apply_cst_transformer,
    read_cst_source_snapshot,
)

from .helpers import post_apply_diagnostics

if TYPE_CHECKING:
    from python_refactor_mcp.backends.jedi_backend import JediBackend
    from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient


_Position = tuple[int, int]


@dataclass(frozen=True)
class _SourceFacts:
    snapshot: CstSourceSnapshot
    module: cst.Module
    positions: dict[cst.CSTNode, CodeRange]
    symbols: symtable.SymbolTable


def _read_source(file_path: str) -> _SourceFacts:
    snapshot = read_cst_source_snapshot(file_path)
    module = snapshot.module
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = dict(wrapper.resolve(PositionProvider))
    try:
        symbols = symtable.symtable(snapshot.source, file_path, "exec")
    except SyntaxError as exc:  # pragma: no cover - LibCST normally reports first
        raise BackendError(f"Cannot build symbol table for {file_path}: {exc}") from exc
    return _SourceFacts(
        snapshot=snapshot,
        module=module,
        positions=positions,
        symbols=symbols,
    )


def _node_position(positions: dict[cst.CSTNode, CodeRange], node: cst.CSTNode) -> _Position:
    position = positions.get(node)
    if position is None:
        raise BackendError("Cannot resolve source position for conversion target")
    return (position.start.line - 1, position.start.column)


def _top_level_function(module: cst.Module, function_name: str) -> cst.FunctionDef:
    matches = [
        statement
        for statement in module.body
        if isinstance(statement, cst.FunctionDef) and statement.name.value == function_name
    ]
    if len(matches) != 1:
        raise BackendError(f"Expected exactly one top-level function named {function_name!r}; found {len(matches)}")
    function = matches[0]
    if function.decorators:
        raise BackendError("Function/method conversion does not support decorated functions")
    return function


def _top_level_class(module: cst.Module, class_name: str) -> cst.ClassDef:
    matches = [
        statement
        for statement in module.body
        if isinstance(statement, cst.ClassDef) and statement.name.value == class_name
    ]
    if len(matches) != 1:
        raise BackendError(f"Expected exactly one top-level class named {class_name!r}; found {len(matches)}")
    source_class = matches[0]
    if source_class.decorators or source_class.bases or source_class.keywords:
        raise BackendError("Function/method conversion requires a plain undecorated class without bases")
    if not isinstance(source_class.body, cst.IndentedBlock):
        raise BackendError("Function/method conversion does not support one-line class bodies")
    return source_class


def _direct_method(source_class: cst.ClassDef, method_name: str) -> cst.FunctionDef:
    if not isinstance(source_class.body, cst.IndentedBlock):  # guarded by _top_level_class
        raise BackendError("Function/method conversion does not support one-line class bodies")
    matches = [
        statement
        for statement in source_class.body.body
        if isinstance(statement, cst.FunctionDef) and statement.name.value == method_name
    ]
    if len(matches) != 1:
        raise BackendError(f"Expected exactly one direct method named {method_name!r}; found {len(matches)}")
    method = matches[0]
    if method.decorators:
        raise BackendError("Function/method conversion does not support decorated methods")
    return method


def _receiver_parameter(function: cst.FunctionDef) -> tuple[str, bool]:
    positional_only = list(function.params.posonly_params)
    ordinary = list(function.params.params)
    parameters = [*positional_only, *ordinary]
    if not parameters:
        raise BackendError("Conversion target must accept a positional receiver parameter")
    receiver = parameters[0]
    if receiver.default is not None:
        raise BackendError("The receiver parameter cannot have a default value")
    return (receiver.name.value, bool(positional_only))


def _class_symbol_table(
    symbols: symtable.SymbolTable,
    class_name: str,
    class_line: int,
) -> symtable.SymbolTable:
    matches = [
        child
        for child in symbols.get_children()
        if child.get_type() == "class" and child.get_name() == class_name and child.get_lineno() == class_line
    ]
    if len(matches) != 1:
        raise BackendError(f"Cannot resolve symbol table for class {class_name!r}")
    return matches[0]


def _normalized_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


async def _semantic_call_positions(
    pyright: PyrightLSPClient,
    jedi: JediBackend,
    file_path: str,
    definition_position: _Position,
) -> set[_Position]:
    references = await find_references(
        pyright,
        jedi,
        file_path,
        definition_position[0],
        definition_position[1],
        include_declaration=True,
    )
    if references.backend_failures:
        failures = ", ".join(
            f"{failure.backend}.{failure.operation}:{failure.error_type}"
            for failure in references.backend_failures
        )
        raise BackendError(
            "Semantic reference discovery was incomplete; refusing a potentially partial "
            f"caller rewrite ({failures})"
        )
    source_path = _normalized_path(file_path)
    external = sorted(
        {
            location.file_path
            for location in references.references
            if _normalized_path(location.file_path) != source_path
        }
    )
    if external:
        raise BackendError(
            "Function/method conversion currently requires all references to be in the "
            f"definition file; found external references in {external!r}"
        )

    positions = {(location.range.start.line, location.range.start.character) for location in references.references}
    if definition_position not in positions:
        raise BackendError(
            "Semantic reference lookup did not return the declaration; refusing a potentially partial caller rewrite"
        )
    positions.remove(definition_position)
    return positions


def _call_name_node(call: cst.Call) -> cst.Name:
    if isinstance(call.func, cst.Name):
        return call.func
    if isinstance(call.func, cst.Attribute):
        return call.func.attr
    raise BackendError("Semantic reference is not a direct function or method call")


class _CallSiteCollector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        reference_positions: set[_Position],
        expected_shape: Literal["function", "method"],
    ) -> None:
        self._reference_positions = reference_positions
        self._expected_shape = expected_shape
        self.supported_positions: set[_Position] = set()

    def visit_Call(self, node: cst.Call) -> None:  # noqa: N802
        if not isinstance(node.func, (cst.Name, cst.Attribute)):
            return
        name = _call_name_node(node)
        code_range = self.get_metadata(PositionProvider, name)
        if not isinstance(code_range, CodeRange):  # pragma: no cover - provider contract
            raise BackendError("Position metadata was unavailable for a reference call")
        position = (code_range.start.line - 1, code_range.start.column)
        if position not in self._reference_positions:
            return
        if self._expected_shape == "function" and not isinstance(node.func, cst.Name):
            return
        if self._expected_shape == "method" and not isinstance(node.func, cst.Attribute):
            return
        self.supported_positions.add(position)


def _validate_call_sites(
    facts: _SourceFacts,
    reference_positions: set[_Position],
    expected_shape: Literal["function", "method"],
) -> None:
    collector = _CallSiteCollector(reference_positions, expected_shape)
    MetadataWrapper(facts.module, unsafe_skip_copy=True).visit(collector)
    unsupported = sorted(reference_positions - collector.supported_positions)
    if unsupported:
        raise BackendError(
            "Function/method conversion only supports direct call references; "
            f"unsupported references at {unsupported!r}"
        )


def _pop_receiver_argument(
    arguments: tuple[cst.Arg, ...],
    receiver_name: str,
    receiver_is_positional_only: bool,
) -> tuple[cst.BaseExpression, tuple[cst.Arg, ...]]:
    if arguments and arguments[0].keyword is None and arguments[0].star == "":
        return (arguments[0].value, arguments[1:])
    if not receiver_is_positional_only:
        matches = [
            index
            for index, argument in enumerate(arguments)
            if argument.keyword is not None and argument.keyword.value == receiver_name and argument.star == ""
        ]
        if len(matches) == 1:
            index = matches[0]
            remaining = [*arguments[:index], *arguments[index + 1 :]]
            if index == len(arguments) - 1 and remaining:
                remaining[-1] = remaining[-1].with_changes(comma=cst.MaybeSentinel.DEFAULT)
            return (arguments[index].value, tuple(remaining))
    raise BackendError(f"A call does not supply receiver parameter {receiver_name!r} as a direct argument")


def _attribute_receiver(expression: cst.BaseExpression) -> cst.BaseExpression:
    """Parenthesize expressions whose precedence would change under attribute access."""
    safe_primaries = (
        cst.Attribute,
        cst.Call,
        cst.Dict,
        cst.DictComp,
        cst.FormattedString,
        cst.GeneratorExp,
        cst.List,
        cst.ListComp,
        cst.Name,
        cst.Set,
        cst.SetComp,
        cst.SimpleString,
        cst.Subscript,
        cst.Tuple,
    )
    if isinstance(expression, safe_primaries) or expression.lpar:
        return expression
    return expression.with_changes(
        lpar=[cst.LeftParen()],
        rpar=[cst.RightParen()],
    )


def _is_pass_only(body: tuple[cst.BaseStatement, ...]) -> bool:
    return (
        len(body) == 1
        and isinstance(body[0], cst.SimpleStatementLine)
        and len(body[0].body) == 1
        and isinstance(body[0].body[0], cst.Pass)
    )


class _FunctionToMethodTransformer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        function_name: str,
        class_name: str,
        receiver_name: str,
        receiver_is_positional_only: bool,
        reference_positions: set[_Position],
    ) -> None:
        self._function_name = function_name
        self._class_name = class_name
        self._receiver_name = receiver_name
        self._receiver_is_positional_only = receiver_is_positional_only
        self._reference_positions = reference_positions

    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.Call:  # noqa: N802
        if not isinstance(original_node.func, cst.Name):
            return updated_node
        code_range = self.get_metadata(PositionProvider, original_node.func)
        if not isinstance(code_range, CodeRange):  # pragma: no cover - provider contract
            raise BackendError("Position metadata was unavailable for a function call")
        position = (code_range.start.line - 1, code_range.start.column)
        if position not in self._reference_positions:
            return updated_node
        receiver, remaining = _pop_receiver_argument(
            tuple(updated_node.args),
            self._receiver_name,
            self._receiver_is_positional_only,
        )
        return updated_node.with_changes(
            func=cst.Attribute(
                value=_attribute_receiver(receiver),
                attr=cst.Name(self._function_name),
            ),
            args=remaining,
        )

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:  # noqa: N802
        moved: cst.FunctionDef | None = None
        remaining: list[cst.BaseStatement] = []
        for original, updated in zip(original_node.body, updated_node.body, strict=True):
            if isinstance(original, cst.FunctionDef) and original.name.value == self._function_name:
                if not isinstance(updated, cst.FunctionDef):  # pragma: no cover - structural invariant
                    raise BackendError("Converted function changed node kind unexpectedly")
                moved = updated
                continue
            remaining.append(updated)
        if moved is None:  # pragma: no cover - prevalidated
            raise BackendError(f"Top-level function {self._function_name!r} disappeared during conversion")

        new_body: list[cst.BaseStatement] = []
        for statement in remaining:
            if isinstance(statement, cst.ClassDef) and statement.name.value == self._class_name:
                if not isinstance(statement.body, cst.IndentedBlock):  # pragma: no cover - prevalidated
                    raise BackendError("Target class body changed shape unexpectedly")
                leading_lines = [
                    line.with_changes(indent=False) if line.comment is None else line for line in moved.leading_lines
                ]
                if not leading_lines:
                    leading_lines = [cst.EmptyLine(indent=False)]
                moved = moved.with_changes(leading_lines=leading_lines)
                class_body = tuple(statement.body.body)
                if _is_pass_only(class_body):
                    class_body = ()
                statement = statement.with_changes(body=statement.body.with_changes(body=[*class_body, moved]))
            new_body.append(statement)
        return updated_node.with_changes(body=new_body)


class _MethodToFunctionTransformer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        method_name: str,
        class_name: str,
        reference_positions: set[_Position],
    ) -> None:
        self._method_name = method_name
        self._class_name = class_name
        self._reference_positions = reference_positions

    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.Call:  # noqa: N802
        if not isinstance(original_node.func, cst.Attribute):
            return updated_node
        code_range = self.get_metadata(PositionProvider, original_node.func.attr)
        if not isinstance(code_range, CodeRange):  # pragma: no cover - provider contract
            raise BackendError("Position metadata was unavailable for a method call")
        position = (code_range.start.line - 1, code_range.start.column)
        if position not in self._reference_positions:
            return updated_node
        if not isinstance(updated_node.func, cst.Attribute):  # pragma: no cover - structural invariant
            raise BackendError("Converted call changed node kind unexpectedly")

        if isinstance(original_node.func.value, cst.Name) and original_node.func.value.value == self._class_name:
            if not updated_node.args:
                raise BackendError("Unbound method call does not supply an instance argument")
            arguments = updated_node.args
        else:
            arguments = (cst.Arg(value=updated_node.func.value), *updated_node.args)
        return updated_node.with_changes(func=cst.Name(self._method_name), args=arguments)

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:  # noqa: N802
        moved: cst.FunctionDef | None = None
        body: list[cst.BaseStatement] = []
        for original, updated in zip(original_node.body, updated_node.body, strict=True):
            if not (
                isinstance(original, cst.ClassDef)
                and original.name.value == self._class_name
                and isinstance(updated, cst.ClassDef)
            ):
                body.append(updated)
                continue
            if not isinstance(updated.body, cst.IndentedBlock):  # pragma: no cover - prevalidated
                raise BackendError("Source class body changed shape unexpectedly")
            class_body: list[cst.BaseStatement] = []
            for original_member, updated_member in zip(
                original.body.body,
                updated.body.body,
                strict=True,
            ):
                if isinstance(original_member, cst.FunctionDef) and original_member.name.value == self._method_name:
                    if not isinstance(updated_member, cst.FunctionDef):  # pragma: no cover
                        raise BackendError("Converted method changed node kind unexpectedly")
                    moved = updated_member
                    continue
                class_body.append(updated_member)
            if not class_body:
                class_body.append(cst.SimpleStatementLine(body=[cst.Pass()]))
            body.append(updated.with_changes(body=updated.body.with_changes(body=class_body)))
            if moved is not None:
                leading_lines = list(moved.leading_lines)
                while len(leading_lines) < 2:
                    leading_lines.insert(0, cst.EmptyLine())
                body.append(moved.with_changes(leading_lines=leading_lines))
        if moved is None:  # pragma: no cover - prevalidated
            raise BackendError(f"Method {self._method_name!r} disappeared during conversion")
        return updated_node.with_changes(body=body)


async def convert_function_to_method(
    pyright: PyrightLSPClient,
    jedi: JediBackend,
    file_path: str,
    function_name: str,
    class_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Move a top-level function into a class and rewrite every direct caller."""
    facts = _read_source(file_path)
    function = _top_level_function(facts.module, function_name)
    source_class = _top_level_class(facts.module, class_name)
    receiver_name, receiver_is_positional_only = _receiver_parameter(function)
    class_symbols = _class_symbol_table(
        facts.symbols,
        class_name,
        _node_position(facts.positions, source_class.name)[0] + 1,
    )
    if function_name in class_symbols.get_identifiers():
        raise BackendError(f"Class {class_name!r} already binds member {function_name!r}")

    definition_position = _node_position(facts.positions, function.name)
    reference_positions = await _semantic_call_positions(
        pyright,
        jedi,
        file_path,
        definition_position,
    )
    _validate_call_sites(facts, reference_positions, "function")
    transformer = _FunctionToMethodTransformer(
        function_name,
        class_name,
        receiver_name,
        receiver_is_positional_only,
        reference_positions,
    )
    edits, files_affected = apply_cst_transformer(
        file_path,
        transformer,
        apply=apply,
        source_snapshot=facts.snapshot,
    )
    result = RefactorResult(
        edits=edits,
        files_affected=files_affected,
        description=(
            f"Converted function {function_name} to {class_name}.{function_name} and "
            f"rewrote {len(reference_positions)} caller(s)"
        ),
        applied=bool(apply and edits),
    )
    if apply and edits:
        return await post_apply_diagnostics(pyright, result)
    return result


async def convert_method_to_function(
    pyright: PyrightLSPClient,
    jedi: JediBackend,
    file_path: str,
    class_name: str,
    method_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Move a direct instance method to module scope and rewrite every caller."""
    facts = _read_source(file_path)
    source_class = _top_level_class(facts.module, class_name)
    method = _direct_method(source_class, method_name)
    _receiver_parameter(method)
    if method_name in facts.symbols.get_identifiers():
        raise BackendError(f"Module already binds top-level name {method_name!r}")

    definition_position = _node_position(facts.positions, method.name)
    reference_positions = await _semantic_call_positions(
        pyright,
        jedi,
        file_path,
        definition_position,
    )
    _validate_call_sites(facts, reference_positions, "method")
    transformer = _MethodToFunctionTransformer(method_name, class_name, reference_positions)
    edits, files_affected = apply_cst_transformer(
        file_path,
        transformer,
        apply=apply,
        source_snapshot=facts.snapshot,
    )
    result = RefactorResult(
        edits=edits,
        files_affected=files_affected,
        description=(
            f"Converted method {class_name}.{method_name} to function {method_name} and "
            f"rewrote {len(reference_positions)} caller(s)"
        ),
        applied=bool(apply and edits),
    )
    if apply and edits:
        return await post_apply_diagnostics(pyright, result)
    return result


__all__ = ["convert_function_to_method", "convert_method_to_function"]
