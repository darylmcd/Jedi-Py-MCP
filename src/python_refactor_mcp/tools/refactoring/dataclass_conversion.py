"""Convert a behavior-free constructor into a standard-library dataclass.

The conversion intentionally accepts a narrow, semantics-preserving source
shape: a plain class whose ``__init__`` contains only ordered
``self.field = field`` assignments. Typed parameters become annotated fields;
missing annotations are resolved through Pyright before the LibCST rewrite.
Anything that could hide behavior fails closed instead of producing a partial
or subtly incompatible dataclass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import libcst as cst
from libcst.metadata import CodePosition, MetadataWrapper, PositionProvider

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import RefactorResult
from python_refactor_mcp.util.cst_apply import (
    apply_cst_transformer,
    read_cst_source_snapshot,
)
from python_refactor_mcp.util.cst_imports import (
    import_alias_binding,
    import_insertion_index,
    reserve_unique_binding,
    top_level_bindings,
)

from .helpers import post_apply_diagnostics

if TYPE_CHECKING:
    from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient


@dataclass(frozen=True)
class _FieldPlan:
    """One constructor parameter promoted to a dataclass field."""

    name: str
    annotation: cst.BaseExpression | None
    default: cst.BaseExpression | None
    position: CodePosition


@dataclass(frozen=True)
class _ConversionPlan:
    """Validated source facts required by the transformer."""

    fields: tuple[_FieldPlan, ...]
    decorator: cst.BaseExpression
    import_alias: str | None


class _CommentFinder(cst.CSTVisitor):
    """Record whether a subtree contains comments that a rewrite could lose."""

    def __init__(self) -> None:
        self.found = False

    def visit_Comment(self, node: cst.Comment) -> None:  # noqa: N802
        self.found = True


def _top_level_class(module: cst.Module, class_name: str) -> cst.ClassDef:
    matches = [
        statement
        for statement in module.body
        if isinstance(statement, cst.ClassDef) and statement.name.value == class_name
    ]
    if not matches:
        raise BackendError(f"Top-level class {class_name!r} not found")
    if len(matches) > 1:
        raise BackendError(f"Multiple top-level classes named {class_name!r} found")
    return matches[0]


def _simple_self_assignment(
    statement: cst.BaseStatement,
) -> tuple[str, cst.Annotation | None] | None:
    """Return ``(field_name, annotation)`` for ``self.x = x`` only."""
    if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
        return None
    small = statement.body[0]
    target: cst.BaseAssignTargetExpression
    value: cst.BaseExpression
    annotation: cst.Annotation | None = None

    if isinstance(small, cst.Assign):
        if len(small.targets) != 1:
            return None
        target = small.targets[0].target
        value = small.value
    elif isinstance(small, cst.AnnAssign) and small.value is not None:
        target = small.target
        value = small.value
        annotation = small.annotation
    else:
        return None

    if not (
        isinstance(target, cst.Attribute)
        and isinstance(target.value, cst.Name)
        and target.value.value == "self"
        and isinstance(value, cst.Name)
        and target.attr.value == value.value
    ):
        return None
    return (target.attr.value, annotation)


def _class_level_name(statement: cst.BaseStatement) -> str | None:
    if isinstance(statement, (cst.ClassDef, cst.FunctionDef)):
        return statement.name.value
    if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
        return None
    small = statement.body[0]
    if isinstance(small, cst.AnnAssign) and isinstance(small.target, cst.Name):
        return small.target.value
    if isinstance(small, cst.Assign) and len(small.targets) == 1 and isinstance(small.targets[0].target, cst.Name):
        return small.targets[0].target.value
    return None


def _is_mutable_default(value: cst.BaseExpression | None) -> bool:
    return isinstance(value, (cst.Dict, cst.DictComp, cst.List, cst.ListComp, cst.Set, cst.SetComp))


def _constructor_fields(
    source_class: cst.ClassDef,
    positions: dict[cst.CSTNode, object],
) -> tuple[_FieldPlan, ...]:
    if source_class.decorators or source_class.bases or source_class.keywords:
        raise BackendError("convert_to_dataclass requires a plain undecorated class without bases")
    if not isinstance(source_class.body, cst.IndentedBlock):
        raise BackendError("convert_to_dataclass does not support one-line class bodies")

    constructors = [
        statement
        for statement in source_class.body.body
        if isinstance(statement, cst.FunctionDef) and statement.name.value == "__init__"
    ]
    if len(constructors) != 1:
        raise BackendError("convert_to_dataclass requires exactly one __init__ method")
    constructor = constructors[0]
    if constructor.decorators or constructor.asynchronous is not None:
        raise BackendError("convert_to_dataclass does not support decorated or async __init__ methods")
    if not isinstance(constructor.body, cst.IndentedBlock):
        raise BackendError("convert_to_dataclass does not support one-line __init__ bodies")

    params = constructor.params
    if (
        params.posonly_params
        or params.kwonly_params
        or params.star_arg is not cst.MaybeSentinel.DEFAULT
        or params.star_kwarg is not None
    ):
        raise BackendError(
            "convert_to_dataclass does not support positional-only, keyword-only, or variadic parameters"
        )
    if not params.params or params.params[0].name.value != "self":
        raise BackendError("convert_to_dataclass requires self as the first constructor parameter")

    finder = _CommentFinder()
    constructor.visit(finder)
    if finder.found:
        raise BackendError("convert_to_dataclass refuses constructors containing comments")

    assignment_names: list[str] = []
    assignment_annotations: dict[str, cst.Annotation] = {}
    for statement in constructor.body.body:
        assignment = _simple_self_assignment(statement)
        if assignment is None:
            raise BackendError("convert_to_dataclass only supports ordered direct self.field = field assignments")
        name, annotation = assignment
        if name in assignment_names:
            raise BackendError(f"Constructor assigns field {name!r} more than once")
        assignment_names.append(name)
        if annotation is not None:
            assignment_annotations[name] = annotation

    constructor_params = list(params.params[1:])
    parameter_names = [param.name.value for param in constructor_params]
    if assignment_names != parameter_names:
        raise BackendError(
            "Constructor assignments must match parameter order exactly; "
            f"parameters={parameter_names!r}, assignments={assignment_names!r}"
        )

    existing_names: set[str] = set()
    for statement in source_class.body.body:
        if statement is constructor:
            continue
        existing_name = _class_level_name(statement)
        if existing_name is not None:
            existing_names.add(existing_name)
    duplicate_fields = existing_names.intersection(parameter_names)
    if duplicate_fields:
        raise BackendError(f"Class already defines field member(s): {sorted(duplicate_fields)!r}")

    fields: list[_FieldPlan] = []
    for param in constructor_params:
        if _is_mutable_default(param.default):
            raise BackendError(f"Mutable default for {param.name.value!r} requires an explicit default_factory")
        position = positions.get(param.name)
        if not isinstance(position, CodePosition):
            raise BackendError(f"Cannot resolve source position for parameter {param.name.value!r}")
        annotation = param.annotation or assignment_annotations.get(param.name.value)
        fields.append(
            _FieldPlan(
                name=param.name.value,
                annotation=annotation.annotation if annotation is not None else None,
                default=param.default,
                position=position,
            )
        )
    return tuple(fields)


def _dataclass_decorator(
    module: cst.Module,
    source_class: cst.ClassDef,
) -> tuple[cst.BaseExpression, str | None]:
    """Return the decorator expression and an optional import alias to add."""
    for statement in module.body:
        if statement is source_class:
            break
        if not isinstance(statement, cst.SimpleStatementLine):
            continue
        for small in statement.body:
            if isinstance(small, cst.ImportFrom) and isinstance(small.module, cst.Name):
                if small.module.value != "dataclasses" or isinstance(small.names, cst.ImportStar):
                    continue
                for alias in small.names:
                    if isinstance(alias.name, cst.Name) and alias.name.value == "dataclass":
                        return (cst.Name(import_alias_binding(alias, from_import=True)), None)
            if isinstance(small, cst.Import):
                for alias in small.names:
                    if isinstance(alias.name, cst.Name) and alias.name.value == "dataclasses":
                        binding = import_alias_binding(alias, from_import=False)
                        return (cst.Attribute(value=cst.Name(binding), attr=cst.Name("dataclass")), None)

    bindings = top_level_bindings(module)
    decorator_binding = reserve_unique_binding(bindings, "dataclass", "_mcp_dataclass")
    return (cst.Name(decorator_binding), decorator_binding)


def _normalize_inferred_annotation(field_name: str, type_string: str) -> cst.BaseExpression:
    raw = type_string.strip().strip("`")
    match = re.fullmatch(rf"\(parameter\)\s+{re.escape(field_name)}\s*:\s*(.+)", raw)
    if match is None:
        match = re.fullmatch(rf"{re.escape(field_name)}\s*:\s*(.+)", raw)
    candidate = (match.group(1) if match is not None else raw).strip()
    if candidate.startswith("builtins."):
        candidate = candidate.removeprefix("builtins.")
    if candidate in {"", "Any", "Unknown", "Unbound", "unknown"} or "Unknown" in candidate:
        raise BackendError(f"Pyright could not infer a concrete type for field {field_name!r}")
    try:
        return cst.parse_expression(candidate)
    except cst.ParserSyntaxError as exc:
        raise BackendError(f"Pyright returned an unusable type for field {field_name!r}: {type_string!r}") from exc


class ConvertToDataclassTransformer(cst.CSTTransformer):
    """Apply a prevalidated conversion plan to one top-level class."""

    def __init__(self, class_name: str, plan: _ConversionPlan) -> None:
        super().__init__()
        self._class_name = class_name
        self._plan = plan
        self.class_found = False
        self._class_depth = 0

    def visit_ClassDef(self, node: cst.ClassDef) -> None:  # noqa: N802
        self._class_depth += 1

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef:  # noqa: N802
        is_top_level = self._class_depth == 1
        self._class_depth -= 1
        if not is_top_level or original_node.name.value != self._class_name:
            return updated_node
        self.class_found = True
        if not isinstance(updated_node.body, cst.IndentedBlock):
            raise BackendError("convert_to_dataclass does not support one-line class bodies")

        replacement_fields = [
            cst.SimpleStatementLine(
                body=[
                    cst.AnnAssign(
                        target=cst.Name(field.name),
                        annotation=cst.Annotation(field.annotation),
                        value=field.default,
                    )
                ]
            )
            for field in self._plan.fields
            if field.annotation is not None
        ]
        if len(replacement_fields) != len(self._plan.fields):
            raise BackendError("convert_to_dataclass received an incomplete field plan")

        body: list[cst.BaseStatement] = []
        for statement in updated_node.body.body:
            if isinstance(statement, cst.FunctionDef) and statement.name.value == "__init__":
                if replacement_fields:
                    replacement_fields[0] = replacement_fields[0].with_changes(leading_lines=statement.leading_lines)
                    body.extend(replacement_fields)
                continue
            body.append(statement)
        if not body:
            body.append(cst.SimpleStatementLine(body=[cst.Pass()]))

        return updated_node.with_changes(
            decorators=[*updated_node.decorators, cst.Decorator(decorator=self._plan.decorator)],
            body=updated_node.body.with_changes(body=body),
        )

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:  # noqa: N802
        if self._plan.import_alias is None:
            return updated_node
        alias = cst.ImportAlias(name=cst.Name("dataclass"))
        if self._plan.import_alias != "dataclass":
            alias = alias.with_changes(asname=cst.AsName(name=cst.Name(self._plan.import_alias)))
        statement = cst.SimpleStatementLine(body=[cst.ImportFrom(module=cst.Name("dataclasses"), names=[alias])])
        body = list(updated_node.body)
        body.insert(import_insertion_index(body), statement)
        return updated_node.with_changes(body=body)


async def convert_to_dataclass(
    pyright: PyrightLSPClient,
    file_path: str,
    class_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Convert a behavior-free constructor to ``@dataclass`` fields.

    Defaults to preview mode. The eligible constructor shape is deliberately
    narrow: ordered direct ``self.field = field`` assignments with ordinary
    positional-or-keyword parameters. Pyright supplies any missing parameter
    annotations. Unsupported source shapes raise :class:`BackendError` without
    modifying the file.
    """
    source_snapshot = read_cst_source_snapshot(file_path)
    module = source_snapshot.module
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    position_ranges = wrapper.resolve(PositionProvider)
    positions: dict[cst.CSTNode, object] = {node: code_range.start for node, code_range in position_ranges.items()}
    source_class = _top_level_class(module, class_name)
    fields = list(_constructor_fields(source_class, positions))
    decorator, import_alias = _dataclass_decorator(module, source_class)

    for index, field in enumerate(fields):
        if field.annotation is not None:
            continue
        type_info = await pyright.get_hover(
            file_path,
            field.position.line - 1,
            field.position.column,
        )
        if type_info is None:
            raise BackendError(f"Pyright returned no type for field {field.name!r}")
        fields[index] = _FieldPlan(
            name=field.name,
            annotation=_normalize_inferred_annotation(field.name, type_info.type_string),
            default=field.default,
            position=field.position,
        )

    plan = _ConversionPlan(fields=tuple(fields), decorator=decorator, import_alias=import_alias)
    transformer = ConvertToDataclassTransformer(class_name, plan)
    edits, files_affected = apply_cst_transformer(
        file_path,
        transformer,
        apply=apply,
        source_snapshot=source_snapshot,
    )
    if not transformer.class_found:
        raise BackendError(f"Top-level class {class_name!r} not found")

    result = RefactorResult(
        edits=edits,
        files_affected=files_affected,
        description=f"Converted {class_name} to a dataclass with {len(fields)} field(s)",
        applied=bool(apply and edits),
    )
    if apply and edits:
        return await post_apply_diagnostics(pyright, result)
    return result


__all__ = ["convert_to_dataclass"]
