"""Convert one narrowly supported validated class into a Pydantic v2 model.

The conversion is intentionally fail-closed.  It accepts a plain class with a
keyword-only, fully annotated constructor whose body contains exactly one
independent ``ValueError`` guard followed by ordered ``self.field = field``
assignments.  The guard becomes a Pydantic v2 ``field_validator`` and the
constructor parameters become model fields.  Broader constructor behavior,
cross-field validation, inheritance, descriptors, and mutable defaults are
rejected before an edit is produced.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING

import libcst as cst
from pydantic import BaseModel as _RuntimeBaseModel

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
    statement_bindings,
    top_level_bindings,
)

from .helpers import post_apply_diagnostics

if TYPE_CHECKING:
    from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient


_SAFE_VALIDATION_NAMES = frozenset(
    {
        "ValueError",
        "bool",
        "bytes",
        "dict",
        "float",
        "int",
        "isinstance",
        "len",
        "list",
        "set",
        "str",
        "tuple",
    }
)
_PYDANTIC_MEMBER_NAMES = frozenset(dir(_RuntimeBaseModel))


@dataclass(frozen=True)
class _FieldPlan:
    name: str
    annotation: cst.BaseExpression
    default: cst.BaseExpression | None


@dataclass(frozen=True)
class _ConversionPlan:
    fields: tuple[_FieldPlan, ...]
    validated_field: str
    validation: cst.If
    validator_name: str
    base_model: cst.BaseExpression
    config_dict: cst.BaseExpression
    field_validator: cst.BaseExpression
    imports: tuple[cst.ImportAlias, ...]


class _CommentFinder(cst.CSTVisitor):
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


def _simple_self_assignment(statement: cst.BaseStatement) -> str | None:
    if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
        return None
    small = statement.body[0]
    if not isinstance(small, cst.Assign) or len(small.targets) != 1:
        return None
    target = small.targets[0].target
    value = small.value
    if not (
        isinstance(target, cst.Attribute)
        and isinstance(target.value, cst.Name)
        and target.value.value == "self"
        and isinstance(value, cst.Name)
        and target.attr.value == value.value
    ):
        return None
    return target.attr.value


def _is_mutable_default(value: cst.BaseExpression | None) -> bool:
    return isinstance(value, (cst.Dict, cst.DictComp, cst.List, cst.ListComp, cst.Set, cst.SetComp))


def _is_docstring(statement: cst.BaseStatement) -> bool:
    return (
        isinstance(statement, cst.SimpleStatementLine)
        and len(statement.body) == 1
        and isinstance(statement.body[0], cst.Expr)
        and isinstance(statement.body[0].value, cst.SimpleString)
    )


def _single_value_error_guard(statement: cst.BaseStatement) -> cst.If | None:
    if not isinstance(statement, cst.If) or statement.orelse is not None:
        return None
    if not isinstance(statement.body, cst.IndentedBlock) or len(statement.body.body) != 1:
        return None
    line = statement.body.body[0]
    if not isinstance(line, cst.SimpleStatementLine) or len(line.body) != 1:
        return None
    raise_statement = line.body[0]
    if not isinstance(raise_statement, cst.Raise) or raise_statement.cause is not None:
        return None
    exception = raise_statement.exc
    return (
        statement
        if isinstance(exception, cst.Call)
        and isinstance(exception.func, cst.Name)
        and exception.func.value == "ValueError"
        else None
    )


def _loaded_names(module: cst.Module, node: cst.CSTNode) -> set[str]:
    try:
        tree = ast.parse(module.code_for_node(node))
    except SyntaxError as exc:  # pragma: no cover - LibCST already parsed the source
        raise BackendError("Cannot analyze constructor validation guard") from exc
    return {child.id for child in ast.walk(tree) if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)}


def _constructor_plan(
    module: cst.Module,
    source_class: cst.ClassDef,
) -> tuple[tuple[_FieldPlan, ...], str, cst.If, str]:
    if source_class.decorators or source_class.bases or source_class.keywords:
        raise BackendError("convert_to_pydantic requires a plain undecorated class without bases")
    if not isinstance(source_class.body, cst.IndentedBlock):
        raise BackendError("convert_to_pydantic does not support one-line class bodies")

    constructors = [
        statement
        for statement in source_class.body.body
        if isinstance(statement, cst.FunctionDef) and statement.name.value == "__init__"
    ]
    if len(constructors) != 1:
        raise BackendError("convert_to_pydantic requires exactly one __init__ method")
    constructor = constructors[0]
    if constructor.decorators or constructor.asynchronous is not None:
        raise BackendError("convert_to_pydantic does not support decorated or async constructors")
    if not isinstance(constructor.body, cst.IndentedBlock):
        raise BackendError("convert_to_pydantic does not support one-line constructors")
    if constructor.returns is not None and not (
        isinstance(constructor.returns.annotation, cst.Name) and constructor.returns.annotation.value == "None"
    ):
        raise BackendError("convert_to_pydantic only supports constructors returning None")

    params = constructor.params
    if (
        params.posonly_params
        or len(params.params) != 1
        or params.params[0].name.value != "self"
        or not isinstance(params.star_arg, cst.ParamStar)
        or params.star_kwarg is not None
        or not params.kwonly_params
    ):
        raise BackendError("convert_to_pydantic requires self plus one or more keyword-only parameters")

    finder = _CommentFinder()
    constructor.visit(finder)
    if finder.found:
        raise BackendError("convert_to_pydantic refuses constructors containing comments")

    fields: list[_FieldPlan] = []
    for parameter in params.kwonly_params:
        if parameter.name.value.startswith("_"):
            raise BackendError("Pydantic model fields cannot start with an underscore")
        if parameter.name.value in _SAFE_VALIDATION_NAMES:
            raise BackendError(f"Field {parameter.name.value!r} conflicts with a reserved validation name")
        if parameter.annotation is None:
            raise BackendError(f"Keyword-only parameter {parameter.name.value!r} requires an annotation")
        if _is_mutable_default(parameter.default):
            raise BackendError(f"Mutable default for {parameter.name.value!r} is not semantics-preserving")
        if parameter.name.value in _PYDANTIC_MEMBER_NAMES or parameter.name.value == "model_config":
            raise BackendError(f"Field {parameter.name.value!r} conflicts with the Pydantic BaseModel API")
        fields.append(
            _FieldPlan(
                name=parameter.name.value,
                annotation=parameter.annotation.annotation,
                default=parameter.default,
            )
        )

    body = list(constructor.body.body)
    validation = _single_value_error_guard(body[0]) if body else None
    if validation is None:
        raise BackendError("convert_to_pydantic requires exactly one leading `if ...: raise ValueError(...)` guard")
    assignments = [_simple_self_assignment(statement) for statement in body[1:]]
    field_names = [field.name for field in fields]
    if assignments != field_names:
        raise BackendError(
            "Constructor assignments must follow the validation guard and match keyword-only "
            f"parameter order exactly; parameters={field_names!r}, assignments={assignments!r}"
        )

    loaded_names = _loaded_names(module, validation)
    referenced_fields = loaded_names.intersection(field_names)
    unsupported_names = loaded_names.difference(referenced_fields, _SAFE_VALIDATION_NAMES)
    if len(referenced_fields) != 1 or unsupported_names:
        raise BackendError(
            "Validation guard must reference exactly one field and only bounded builtins; "
            f"fields={sorted(referenced_fields)!r}, unsupported={sorted(unsupported_names)!r}"
        )
    validated_field = next(iter(referenced_fields))
    validated_plan = next(field for field in fields if field.name == validated_field)
    if validated_plan.default is not None:
        raise BackendError("The validated field cannot have a default value")

    existing_names: set[str] = set()
    for statement in source_class.body.body:
        if statement is constructor or _is_docstring(statement):
            continue
        if not isinstance(statement, cst.FunctionDef) or statement.decorators:
            raise BackendError(
                "convert_to_pydantic only preserves undecorated methods outside __init__; "
                "descriptors and class data are unsupported"
            )
        existing_names.add(statement.name.value)
    collisions = existing_names.intersection(_PYDANTIC_MEMBER_NAMES)
    if collisions:
        raise BackendError(f"Class member(s) conflict with BaseModel: {sorted(collisions)!r}")

    validator_name = f"_validate_{validated_field}"
    suffix = 2
    while validator_name in existing_names or validator_name in field_names:
        validator_name = f"_validate_{validated_field}_{suffix}"
        suffix += 1
    return (tuple(fields), validated_field, validation, validator_name)


def _pydantic_references(
    module: cst.Module,
    source_class: cst.ClassDef,
) -> tuple[cst.BaseExpression, cst.BaseExpression, cst.BaseExpression, tuple[cst.ImportAlias, ...]]:
    references: dict[str, cst.BaseExpression] = {}
    reference_bindings: dict[str, str] = {}
    for statement in module.body:
        if statement is source_class:
            break
        bound_names = statement_bindings(statement)
        for public_name, binding in tuple(reference_bindings.items()):
            if binding in bound_names:
                references.pop(public_name, None)
                reference_bindings.pop(public_name)
        if not isinstance(statement, cst.SimpleStatementLine):
            continue
        for small in statement.body:
            if isinstance(small, cst.Import):
                for alias in small.names:
                    if cst.Module([]).code_for_node(alias.name) == "pydantic":
                        module_binding = import_alias_binding(alias, from_import=False)
                        for public_name in ("BaseModel", "ConfigDict", "field_validator"):
                            references[public_name] = cst.Attribute(
                                value=cst.Name(module_binding),
                                attr=cst.Name(public_name),
                            )
                            reference_bindings[public_name] = module_binding
            elif (
                isinstance(small, cst.ImportFrom)
                and small.module is not None
                and cst.Module([]).code_for_node(small.module) == "pydantic"
            ):
                if isinstance(small.names, cst.ImportStar):
                    raise BackendError("convert_to_pydantic does not support wildcard Pydantic imports")
                for alias in small.names:
                    imported_name = cst.Module([]).code_for_node(alias.name)
                    if imported_name in {"BaseModel", "ConfigDict", "field_validator"}:
                        binding = import_alias_binding(alias, from_import=True)
                        references[imported_name] = cst.Name(binding)
                        reference_bindings[imported_name] = binding

    bindings = top_level_bindings(module)
    imports: list[cst.ImportAlias] = []
    for public_name in ("BaseModel", "ConfigDict", "field_validator"):
        if public_name in references:
            continue
        binding = reserve_unique_binding(
            bindings,
            public_name,
            f"_mcp_pydantic_{public_name.lower()}",
        )
        alias = cst.ImportAlias(name=cst.Name(public_name))
        if binding != public_name:
            alias = alias.with_changes(asname=cst.AsName(name=cst.Name(binding)))
        imports.append(alias)
        references[public_name] = cst.Name(binding)

    return (
        references["BaseModel"],
        references["ConfigDict"],
        references["field_validator"],
        tuple(imports),
    )


class _ParameterToValueTransformer(cst.CSTTransformer):
    def __init__(self, parameter_name: str) -> None:
        self._parameter_name = parameter_name

    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:  # noqa: N802
        return cst.Name("value") if original_node.value == self._parameter_name else updated_node

    def leave_Attribute(self, original_node: cst.Attribute, updated_node: cst.Attribute) -> cst.Attribute:  # noqa: N802
        return updated_node.with_changes(attr=original_node.attr)

    def leave_Arg(self, original_node: cst.Arg, updated_node: cst.Arg) -> cst.Arg:  # noqa: N802
        return updated_node.with_changes(keyword=original_node.keyword)


class ConvertToPydanticTransformer(cst.CSTTransformer):
    def __init__(self, class_name: str, plan: _ConversionPlan) -> None:
        super().__init__()
        self._class_name = class_name
        self._plan = plan
        self._class_depth = 0
        self.class_found = False

    def visit_ClassDef(self, node: cst.ClassDef) -> None:  # noqa: N802
        self._class_depth += 1

    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.ClassDef:  # noqa: N802
        is_target = self._class_depth == 1 and original_node.name.value == self._class_name
        self._class_depth -= 1
        if not is_target:
            return updated_node
        self.class_found = True
        if not isinstance(updated_node.body, cst.IndentedBlock):
            raise BackendError("convert_to_pydantic does not support one-line class bodies")

        constructor = next(
            statement
            for statement in updated_node.body.body
            if isinstance(statement, cst.FunctionDef) and statement.name.value == "__init__"
        )
        config = cst.SimpleStatementLine(
            body=[
                cst.Assign(
                    targets=[cst.AssignTarget(cst.Name("model_config"))],
                    value=cst.Call(
                        func=self._plan.config_dict,
                        args=[
                            cst.Arg(
                                keyword=cst.Name("extra"),
                                value=cst.SimpleString('"forbid"'),
                                equal=cst.AssignEqual(
                                    whitespace_before=cst.SimpleWhitespace(""),
                                    whitespace_after=cst.SimpleWhitespace(""),
                                ),
                            )
                        ],
                    ),
                )
            ],
            leading_lines=constructor.leading_lines,
        )
        field_lines = [
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
        ]
        validated_field = next(field for field in self._plan.fields if field.name == self._plan.validated_field)
        rewritten_guard = cst.ensure_type(
            self._plan.validation.visit(_ParameterToValueTransformer(self._plan.validated_field)),
            cst.If,
        )
        validator = cst.FunctionDef(
            name=cst.Name(self._plan.validator_name),
            params=cst.Parameters(
                params=[
                    cst.Param(name=cst.Name("cls")),
                    cst.Param(
                        name=cst.Name("value"),
                        annotation=cst.Annotation(validated_field.annotation),
                    ),
                ]
            ),
            body=cst.IndentedBlock(
                body=[
                    rewritten_guard,
                    cst.SimpleStatementLine(body=[cst.Return(value=cst.Name("value"))]),
                ]
            ),
            decorators=[
                cst.Decorator(
                    decorator=cst.Call(
                        func=self._plan.field_validator,
                        args=[cst.Arg(cst.SimpleString(repr(self._plan.validated_field)))],
                    )
                ),
                cst.Decorator(decorator=cst.Name("classmethod")),
            ],
            returns=cst.Annotation(validated_field.annotation),
        )

        body: list[cst.BaseStatement] = []
        inserted_fields = False
        for statement in updated_node.body.body:
            if statement is constructor:
                body.extend([config, *field_lines, validator])
                inserted_fields = True
            else:
                body.append(statement)
        if not inserted_fields:  # pragma: no cover - plan and transform use the same parsed source
            raise BackendError("Validated constructor disappeared during Pydantic conversion")

        return updated_node.with_changes(
            bases=[cst.Arg(value=self._plan.base_model)],
            body=updated_node.body.with_changes(body=body),
        )

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:  # noqa: N802
        if not self._plan.imports:
            return updated_node
        statement = cst.SimpleStatementLine(
            body=[cst.ImportFrom(module=cst.Name("pydantic"), names=list(self._plan.imports))]
        )
        body = list(updated_node.body)
        body.insert(import_insertion_index(body), statement)
        return updated_node.with_changes(body=body)


async def convert_to_pydantic(
    pyright: PyrightLSPClient,
    file_path: str,
    class_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Convert a bounded keyword-only validated class to a Pydantic v2 model."""
    source_snapshot = read_cst_source_snapshot(file_path)
    module = source_snapshot.module
    source_class = _top_level_class(module, class_name)
    fields, validated_field, validation, validator_name = _constructor_plan(module, source_class)
    base_model, config_dict, field_validator, imports = _pydantic_references(
        module,
        source_class,
    )
    plan = _ConversionPlan(
        fields=fields,
        validated_field=validated_field,
        validation=validation,
        validator_name=validator_name,
        base_model=base_model,
        config_dict=config_dict,
        field_validator=field_validator,
        imports=imports,
    )
    transformer = ConvertToPydanticTransformer(class_name, plan)
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
        description=(
            f"Converted {class_name} to a Pydantic v2 model with {len(fields)} field(s) "
            f"and validation for {validated_field}"
        ),
        applied=bool(apply and edits),
    )
    if apply and edits:
        return await post_apply_diagnostics(pyright, result)
    return result


__all__ = ["convert_to_pydantic"]
