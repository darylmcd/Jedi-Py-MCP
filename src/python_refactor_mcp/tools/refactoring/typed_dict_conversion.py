"""Convert consistent dict-literal function returns into a ``TypedDict``.

The transform deliberately accepts a narrow source shape. A top-level function
must return only dictionary literals whose ordered string keys agree across all
branches. Pyright supplies the value types, and every branch must resolve each
field to the same concrete annotation. Dynamic keys, unpacking, ambiguous
types, and unsupported existing return annotations fail before an edit is
produced.
"""

from __future__ import annotations

import ast
import keyword
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import libcst as cst
from libcst.metadata import CodePosition, MetadataWrapper, PositionProvider

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import RefactorResult
from python_refactor_mcp.util.cst_apply import apply_cst_transformer, parse_module

from .helpers import post_apply_diagnostics

if TYPE_CHECKING:
    from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient


_DICT_ANNOTATION_NAMES = frozenset({"dict", "Dict", "Mapping", "MutableMapping"})
_UNKNOWN_TYPE_PATTERN = re.compile(r"\b(?:Any|Unknown|Unbound)\b", re.IGNORECASE)


@dataclass(frozen=True)
class _ReturnField:
    """One field value and its source position in a return dictionary."""

    name: str
    position: CodePosition


@dataclass(frozen=True)
class _TypedDictPlan:
    """Validated facts needed to rewrite one function."""

    function_name: str
    typed_dict_name: str
    fields: tuple[tuple[str, cst.BaseExpression], ...]
    base: cst.BaseExpression
    import_statement: cst.SimpleStatementLine | None


class _ReturnCollector(cst.CSTVisitor):
    """Collect returns from one function body while skipping nested scopes."""

    def __init__(self) -> None:
        self.returns: list[cst.Return] = []

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:  # noqa: N802
        return False

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:  # noqa: N802
        return False

    def visit_Lambda(self, node: cst.Lambda) -> bool:  # noqa: N802
        return False

    def visit_Return(self, node: cst.Return) -> None:  # noqa: N802
        self.returns.append(node)


def _top_level_function(module: cst.Module, function_name: str) -> cst.FunctionDef:
    matches = [
        statement
        for statement in module.body
        if isinstance(statement, cst.FunctionDef) and statement.name.value == function_name
    ]
    if not matches:
        raise BackendError(f"Top-level function {function_name!r} not found")
    if len(matches) > 1:
        raise BackendError(f"Multiple top-level functions named {function_name!r} found")
    return matches[0]


def _string_key(expression: cst.BaseExpression) -> str | None:
    if not isinstance(expression, cst.SimpleString):
        return None
    try:
        value = ast.literal_eval(expression.value)
    except (SyntaxError, ValueError):
        return None
    return value if isinstance(value, str) else None


def _return_fields(
    function: cst.FunctionDef,
    positions: dict[cst.CSTNode, object],
) -> tuple[tuple[_ReturnField, ...], ...]:
    collector = _ReturnCollector()
    function.body.visit(collector)
    if not collector.returns:
        raise BackendError("convert_to_typeddict requires at least one return statement")

    returns: list[tuple[_ReturnField, ...]] = []
    expected_names: tuple[str, ...] | None = None
    for return_node in collector.returns:
        if not isinstance(return_node.value, cst.Dict):
            raise BackendError("convert_to_typeddict only supports dict-literal return values")
        fields: list[_ReturnField] = []
        seen: set[str] = set()
        for element in return_node.value.elements:
            if not isinstance(element, cst.DictElement):
                raise BackendError("convert_to_typeddict does not support dictionary unpacking")
            name = _string_key(element.key)
            if name is None or not name.isidentifier() or keyword.iskeyword(name):
                raise BackendError(
                    "convert_to_typeddict requires unique string keys that are valid identifiers"
                )
            if name in seen:
                raise BackendError(f"Return dictionary contains duplicate key {name!r}")
            seen.add(name)
            position = positions.get(element.value)
            if not isinstance(position, CodePosition):
                raise BackendError(f"Cannot resolve source position for field {name!r}")
            fields.append(_ReturnField(name=name, position=position))

        names = tuple(field.name for field in fields)
        if not names:
            raise BackendError("convert_to_typeddict requires at least one dictionary field")
        if expected_names is None:
            expected_names = names
        elif names != expected_names:
            raise BackendError(
                "All return dictionaries must use the same ordered keys; "
                f"expected={expected_names!r}, found={names!r}"
            )
        returns.append(tuple(fields))
    return tuple(returns)


def _annotation_from_hover(field_name: str, type_string: str) -> cst.BaseExpression:
    raw = type_string.strip().strip("`")
    match = re.fullmatch(r"\([^)]+\)\s+[^:\n]+:\s*(.+)", raw)
    candidate = (match.group(1) if match is not None else raw).strip()
    candidate = candidate.replace("builtins.", "")
    if not candidate or _UNKNOWN_TYPE_PATTERN.search(candidate):
        raise BackendError(f"Pyright could not infer a concrete type for field {field_name!r}")
    candidate = _widen_literal_type(field_name, candidate)
    try:
        return cst.parse_expression(candidate)
    except cst.ParserSyntaxError as exc:
        raise BackendError(
            f"Pyright returned an unusable type for field {field_name!r}: {type_string!r}"
        ) from exc


def _widen_literal_type(field_name: str, candidate: str) -> str:
    """Widen Pyright ``Literal`` hovers without adding an unbound typing name."""
    try:
        expression = ast.parse(candidate, mode="eval").body
    except SyntaxError:
        return candidate
    if not isinstance(expression, ast.Subscript):
        return candidate
    base = expression.value
    is_literal = isinstance(base, ast.Name) and base.id == "Literal"
    is_typing_literal = (
        isinstance(base, ast.Attribute)
        and isinstance(base.value, ast.Name)
        and base.value.id == "typing"
        and base.attr == "Literal"
    )
    if not (is_literal or is_typing_literal):
        return candidate

    values = expression.slice.elts if isinstance(expression.slice, ast.Tuple) else [expression.slice]
    type_names: list[str] = []
    primitive_names = {
        str: "str",
        bytes: "bytes",
        bool: "bool",
        int: "int",
        float: "float",
        complex: "complex",
        type(None): "None",
    }
    for value_node in values:
        try:
            value = ast.literal_eval(value_node)
        except (ValueError, TypeError):
            raise BackendError(
                f"Pyright inferred a non-primitive Literal type for field {field_name!r}"
            ) from None
        type_name = primitive_names.get(type(value))
        if type_name is None:
            raise BackendError(
                f"Pyright inferred an unsupported Literal type for field {field_name!r}"
            )
        if type_name not in type_names:
            type_names.append(type_name)
    return " | ".join(type_names)


def _annotation_name(annotation: cst.BaseExpression) -> str | None:
    expression = annotation.value if isinstance(annotation, cst.Subscript) else annotation
    if isinstance(expression, cst.Name):
        return expression.value
    if isinstance(expression, cst.Attribute):
        return expression.attr.value
    return None


def _validate_return_annotation(function: cst.FunctionDef) -> None:
    if function.returns is None:
        return
    name = _annotation_name(function.returns.annotation)
    if name not in _DICT_ANNOTATION_NAMES:
        raise BackendError(
            "convert_to_typeddict only replaces absent or dict/mapping return annotations"
        )


def _bound_names(module: cst.Module) -> set[str]:
    bindings: set[str] = set()
    for statement in module.body:
        if isinstance(statement, (cst.ClassDef, cst.FunctionDef)):
            bindings.add(statement.name.value)
            continue
        if not isinstance(statement, cst.SimpleStatementLine):
            continue
        for small in statement.body:
            if isinstance(small, cst.Assign):
                for target in small.targets:
                    if isinstance(target.target, cst.Name):
                        bindings.add(target.target.value)
            elif isinstance(small, cst.AnnAssign) and isinstance(small.target, cst.Name):
                bindings.add(small.target.value)
            elif isinstance(small, cst.Import):
                for alias in small.names:
                    if alias.asname is not None and isinstance(alias.asname.name, cst.Name):
                        bindings.add(alias.asname.name.value)
                    else:
                        bindings.add(cst.Module([]).code_for_node(alias.name).split(".", 1)[0])
            elif isinstance(small, cst.ImportFrom) and not isinstance(small.names, cst.ImportStar):
                for alias in small.names:
                    if alias.asname is not None and isinstance(alias.asname.name, cst.Name):
                        bindings.add(alias.asname.name.value)
                    elif isinstance(alias.name, cst.Name):
                        bindings.add(alias.name.value)
    return bindings


def _typed_dict_base(
    module: cst.Module,
    bindings: set[str],
) -> tuple[cst.BaseExpression, cst.SimpleStatementLine | None]:
    for statement in module.body[: _import_end_index(module.body)]:
        if not isinstance(statement, cst.SimpleStatementLine):
            continue
        for small in statement.body:
            if isinstance(small, cst.ImportFrom) and isinstance(small.module, cst.Name):
                if small.module.value != "typing" or isinstance(small.names, cst.ImportStar):
                    continue
                for alias in small.names:
                    if isinstance(alias.name, cst.Name) and alias.name.value == "TypedDict":
                        if alias.asname is not None and isinstance(alias.asname.name, cst.Name):
                            return (cst.Name(alias.asname.name.value), None)
                        return (cst.Name("TypedDict"), None)
            if isinstance(small, cst.Import):
                for alias in small.names:
                    if isinstance(alias.name, cst.Name) and alias.name.value == "typing":
                        binding = (
                            alias.asname.name.value
                            if alias.asname is not None and isinstance(alias.asname.name, cst.Name)
                            else "typing"
                        )
                        return (
                            cst.Attribute(value=cst.Name(binding), attr=cst.Name("TypedDict")),
                            None,
                        )

    import_binding = "TypedDict"
    if import_binding in bindings:
        import_binding = "_mcp_TypedDict"
        suffix = 2
        while import_binding in bindings:
            import_binding = f"_mcp_TypedDict_{suffix}"
            suffix += 1
    alias = cst.ImportAlias(name=cst.Name("TypedDict"))
    if import_binding != "TypedDict":
        alias = alias.with_changes(asname=cst.AsName(name=cst.Name(import_binding)))
    statement = cst.SimpleStatementLine(
        body=[cst.ImportFrom(module=cst.Name("typing"), names=[alias])]
    )
    return (cst.Name(import_binding), statement)


def _import_end_index(body: Sequence[cst.BaseStatement]) -> int:
    index = 0
    if body and isinstance(body[0], cst.SimpleStatementLine):
        first = body[0].body
        if len(first) == 1 and isinstance(first[0], cst.Expr) and isinstance(first[0].value, cst.SimpleString):
            index = 1
    while index < len(body):
        statement = body[index]
        if not isinstance(statement, cst.SimpleStatementLine) or not statement.body:
            break
        if not all(isinstance(small, (cst.Import, cst.ImportFrom)) for small in statement.body):
            break
        index += 1
    return index


class ConvertToTypedDictTransformer(cst.CSTTransformer):
    """Apply a validated TypedDict plan to one top-level function."""

    def __init__(self, plan: _TypedDictPlan) -> None:
        super().__init__()
        self._plan = plan
        self._function_depth = 0
        self.function_found = False

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:  # noqa: N802
        self._function_depth += 1

    def leave_FunctionDef(  # noqa: N802
        self,
        original_node: cst.FunctionDef,
        updated_node: cst.FunctionDef,
    ) -> cst.FunctionDef:
        is_target = self._function_depth == 1 and original_node.name.value == self._plan.function_name
        self._function_depth -= 1
        if not is_target:
            return updated_node
        self.function_found = True
        return updated_node.with_changes(
            returns=cst.Annotation(annotation=cst.Name(self._plan.typed_dict_name))
        )

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:  # noqa: N802
        fields = [
            cst.SimpleStatementLine(
                body=[
                    cst.AnnAssign(
                        target=cst.Name(name),
                        annotation=cst.Annotation(annotation),
                    )
                ]
            )
            for name, annotation in self._plan.fields
        ]
        typed_dict = cst.ClassDef(
            name=cst.Name(self._plan.typed_dict_name),
            bases=[cst.Arg(value=self._plan.base)],
            body=cst.IndentedBlock(body=fields),
        )
        body = list(updated_node.body)
        insert_at = _import_end_index(tuple(body))
        if self._plan.import_statement is not None:
            body.insert(insert_at, self._plan.import_statement)
            insert_at += 1
        if insert_at > 0:
            typed_dict = typed_dict.with_changes(leading_lines=[cst.EmptyLine()])
        body.insert(insert_at, typed_dict)
        return updated_node.with_changes(body=body)


async def convert_to_typeddict(
    pyright: PyrightLSPClient,
    file_path: str,
    function_name: str,
    typed_dict_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Convert consistent dict-literal returns to a generated ``TypedDict``."""
    if not typed_dict_name.isidentifier() or keyword.iskeyword(typed_dict_name):
        raise BackendError("typed_dict_name must be a valid non-keyword Python identifier")
    try:
        source = Path(file_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeError) as exc:
        raise BackendError(f"Cannot read file for TypedDict conversion: {exc}") from exc

    module = parse_module(source, file_path)
    bindings = _bound_names(module)
    if typed_dict_name in bindings:
        raise BackendError(f"Top-level name {typed_dict_name!r} already exists")
    function = _top_level_function(module, function_name)
    _validate_return_annotation(function)

    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    position_ranges = wrapper.resolve(PositionProvider)
    positions: dict[cst.CSTNode, object] = {
        node: code_range.start for node, code_range in position_ranges.items()
    }
    return_fields = _return_fields(function, positions)

    inferred: dict[str, str] = {}
    annotations: dict[str, cst.BaseExpression] = {}
    for fields in return_fields:
        for field in fields:
            type_info = await pyright.get_hover(
                file_path,
                field.position.line - 1,
                field.position.column,
            )
            if type_info is None:
                raise BackendError(f"Pyright returned no type for field {field.name!r}")
            annotation = _annotation_from_hover(field.name, type_info.type_string)
            rendered = cst.Module([]).code_for_node(annotation)
            prior = inferred.setdefault(field.name, rendered)
            if prior != rendered:
                raise BackendError(
                    f"Field {field.name!r} has inconsistent inferred types: {prior!r} and {rendered!r}"
                )
            annotations.setdefault(field.name, annotation)

    base, import_statement = _typed_dict_base(module, bindings)
    ordered_names = tuple(field.name for field in return_fields[0])
    plan = _TypedDictPlan(
        function_name=function_name,
        typed_dict_name=typed_dict_name,
        fields=tuple((name, annotations[name]) for name in ordered_names),
        base=base,
        import_statement=import_statement,
    )
    transformer = ConvertToTypedDictTransformer(plan)
    edits, files_affected = apply_cst_transformer(file_path, transformer, apply=apply)
    if not transformer.function_found:
        raise BackendError(f"Top-level function {function_name!r} not found")

    result = RefactorResult(
        edits=edits,
        files_affected=files_affected,
        description=(
            f"Converted {function_name} return dictionaries to {typed_dict_name} "
            f"with {len(ordered_names)} field(s)"
        ),
        applied=bool(apply and edits),
    )
    if apply and edits:
        return await post_apply_diagnostics(pyright, result)
    return result


__all__ = ["convert_to_typeddict"]
