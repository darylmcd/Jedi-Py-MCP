"""Extract a cohesive set of instance fields and methods into a collaborator.

The transform is deliberately conservative. It operates on one top-level class,
requires a plain ``__init__``, and rejects source shapes whose behavior cannot be
preserved locally. Selected fields must be direct ``self.field = value`` (or
annotated) constructor assignments. Selected methods must be plain synchronous
instance methods and may only access other selected members through ``self``.

The source object keeps its public surface: field properties and method delegates
forward to a newly-created collaborator stored on ``self``. This lets callers and
remaining source methods continue using the original member names while the
implementation state and behavior move together.
"""

from __future__ import annotations

import keyword
from collections.abc import Sequence
from dataclasses import dataclass

import libcst as cst

from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient
from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import RefactorResult
from python_refactor_mcp.util.cst_apply import apply_cst_transformer

from .helpers import post_apply_diagnostics


@dataclass(frozen=True)
class _FieldPlan:
    name: str
    annotation: cst.Annotation | None


def _is_identifier(value: str) -> bool:
    return value.isidentifier() and not keyword.iskeyword(value)


def _self_attribute(name: str) -> cst.Attribute:
    return cst.Attribute(value=cst.Name("self"), attr=cst.Name(name))


def _collaborator_member(attribute_name: str, member_name: str) -> cst.Attribute:
    return cst.Attribute(value=_self_attribute(attribute_name), attr=cst.Name(member_name))


def _direct_self_assignment(
    statement: cst.BaseStatement,
) -> list[tuple[str, cst.Annotation | None]]:
    """Return direct ``self.name`` assignments from one constructor statement."""
    if not isinstance(statement, cst.SimpleStatementLine):
        return []

    assignments: list[tuple[str, cst.Annotation | None]] = []
    for small in statement.body:
        if isinstance(small, cst.Assign) and len(small.targets) == 1:
            target = small.targets[0].target
            if (
                isinstance(target, cst.Attribute)
                and isinstance(target.value, cst.Name)
                and target.value.value == "self"
            ):
                assignments.append((target.attr.value, None))
        elif isinstance(small, cst.AnnAssign):
            target = small.target
            if (
                isinstance(target, cst.Attribute)
                and isinstance(target.value, cst.Name)
                and target.value.value == "self"
                and small.value is not None
            ):
                assignments.append((target.attr.value, small.annotation))
    return assignments


def _replace_selected_field_assignments(
    statement: cst.BaseStatement,
    field_names: set[str],
    collaborator_attribute: str,
) -> cst.BaseStatement:
    if not isinstance(statement, cst.SimpleStatementLine):
        return statement

    changed = False
    new_body: list[cst.BaseSmallStatement] = []
    for small in statement.body:
        replacement: cst.BaseSmallStatement = small
        if isinstance(small, cst.Assign) and len(small.targets) == 1:
            target = small.targets[0].target
            if (
                isinstance(target, cst.Attribute)
                and isinstance(target.value, cst.Name)
                and target.value.value == "self"
                and target.attr.value in field_names
            ):
                replacement = small.with_changes(
                    targets=[
                        small.targets[0].with_changes(
                            target=_collaborator_member(collaborator_attribute, target.attr.value)
                        )
                    ]
                )
                changed = True
        elif isinstance(small, cst.AnnAssign):
            target = small.target
            if (
                isinstance(target, cst.Attribute)
                and isinstance(target.value, cst.Name)
                and target.value.value == "self"
                and target.attr.value in field_names
            ):
                replacement = small.with_changes(target=_collaborator_member(collaborator_attribute, target.attr.value))
                changed = True
        new_body.append(replacement)
    return statement.with_changes(body=new_body) if changed else statement


class _SelfAttributeVisitor(cst.CSTVisitor):
    """Collect direct ``self.name`` uses while ignoring nested classes."""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:  # noqa: N802
        return False

    def visit_Attribute(self, node: cst.Attribute) -> bool:  # noqa: N802
        if isinstance(node.value, cst.Name) and node.value.value == "self":
            self.names.add(node.attr.value)
            return False
        return True


class _MovedMethodSafetyVisitor(_SelfAttributeVisitor):
    """Find method shapes that cannot be moved without changing behavior."""

    def __init__(self) -> None:
        super().__init__()
        self.uses_bare_self = False
        self.uses_super = False
        self.yields = False

    def visit_Name(self, node: cst.Name) -> None:  # noqa: N802
        if node.value == "self":
            self.uses_bare_self = True

    def visit_Call(self, node: cst.Call) -> None:  # noqa: N802
        if isinstance(node.func, cst.Name) and node.func.value == "super":
            self.uses_super = True

    def visit_Yield(self, node: cst.Yield) -> None:  # noqa: N802
        self.yields = True


def _module_binding_names(module: cst.Module) -> set[str]:
    """Collect common direct module bindings for new-class collision checks."""
    names: set[str] = set()
    for statement in module.body:
        if isinstance(statement, (cst.ClassDef, cst.FunctionDef)):
            names.add(statement.name.value)
            continue
        if not isinstance(statement, cst.SimpleStatementLine):
            continue
        for small in statement.body:
            if isinstance(small, cst.Assign):
                for target in small.targets:
                    if isinstance(target.target, cst.Name):
                        names.add(target.target.value)
            elif isinstance(small, cst.AnnAssign) and isinstance(small.target, cst.Name):
                names.add(small.target.value)
            elif isinstance(small, cst.Import):
                for alias in small.names:
                    if alias.asname is not None and isinstance(alias.asname.name, cst.Name):
                        names.add(alias.asname.name.value)
                    else:
                        imported: cst.BaseExpression = alias.name
                        while isinstance(imported, cst.Attribute):
                            imported = imported.value
                        if isinstance(imported, cst.Name):
                            names.add(imported.value)
            elif isinstance(small, cst.ImportFrom) and not isinstance(small.names, cst.ImportStar):
                for alias in small.names:
                    if alias.asname is not None and isinstance(alias.asname.name, cst.Name):
                        names.add(alias.asname.name.value)
                    elif isinstance(alias.name, cst.Name):
                        names.add(alias.name.value)
                    else:
                        names.add(alias.name.attr.value)
    return names


def _is_docstring_statement(statement: cst.BaseStatement) -> bool:
    if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
        return False
    expression = statement.body[0]
    return isinstance(expression, cst.Expr) and isinstance(expression.value, (cst.SimpleString, cst.ConcatenatedString))


def _docstring_statement(method: cst.FunctionDef) -> cst.BaseStatement | None:
    if not isinstance(method.body, cst.IndentedBlock) or not method.body.body:
        return None
    first = method.body.body[0]
    return first if _is_docstring_statement(first) else None


def _forward_arguments(method: cst.FunctionDef) -> list[cst.Arg]:
    params = method.params
    positional = [*params.posonly_params, *params.params]
    if not positional or positional[0].name.value != "self":
        raise BackendError(f"Cannot extract method {method.name.value!r}: first parameter must be self")

    arguments = [cst.Arg(value=cst.Name(param.name.value)) for param in positional[1:]]
    if isinstance(params.star_arg, cst.Param):
        arguments.append(cst.Arg(value=cst.Name(params.star_arg.name.value), star="*"))
    arguments.extend(
        cst.Arg(
            value=cst.Name(param.name.value),
            keyword=cst.Name(param.name.value),
            equal=cst.AssignEqual(
                whitespace_before=cst.SimpleWhitespace(""),
                whitespace_after=cst.SimpleWhitespace(""),
            ),
        )
        for param in params.kwonly_params
    )
    if params.star_kwarg is not None:
        arguments.append(cst.Arg(value=cst.Name(params.star_kwarg.name.value), star="**"))
    return arguments


def _delegate_method(method: cst.FunctionDef, collaborator_attribute: str) -> cst.FunctionDef:
    call = cst.Call(
        func=_collaborator_member(collaborator_attribute, method.name.value),
        args=_forward_arguments(method),
    )
    body: list[cst.BaseStatement] = []
    docstring = _docstring_statement(method)
    if docstring is not None:
        body.append(docstring)
    body.append(cst.SimpleStatementLine(body=[cst.Return(value=call)]))
    return method.with_changes(body=cst.IndentedBlock(body=body))


def _field_properties(field: _FieldPlan, collaborator_attribute: str) -> list[cst.FunctionDef]:
    getter = cst.FunctionDef(
        name=cst.Name(field.name),
        params=cst.Parameters(params=[cst.Param(name=cst.Name("self"))]),
        body=cst.IndentedBlock(
            body=[
                cst.SimpleStatementLine(
                    body=[cst.Return(value=_collaborator_member(collaborator_attribute, field.name))]
                )
            ]
        ),
        decorators=[cst.Decorator(decorator=cst.Name("property"))],
        returns=field.annotation,
    )
    setter = cst.FunctionDef(
        name=cst.Name(field.name),
        params=cst.Parameters(
            params=[
                cst.Param(name=cst.Name("self")),
                cst.Param(name=cst.Name("value"), annotation=field.annotation),
            ]
        ),
        body=cst.IndentedBlock(
            body=[
                cst.SimpleStatementLine(
                    body=[
                        cst.Assign(
                            targets=[cst.AssignTarget(target=_collaborator_member(collaborator_attribute, field.name))],
                            value=cst.Name("value"),
                        )
                    ]
                )
            ]
        ),
        decorators=[cst.Decorator(decorator=cst.Attribute(value=cst.Name(field.name), attr=cst.Name("setter")))],
    )
    return [getter, setter]


def _collaborator_assignment(new_class_name: str, collaborator_attribute: str) -> cst.BaseStatement:
    return cst.SimpleStatementLine(
        body=[
            cst.Assign(
                targets=[cst.AssignTarget(target=_self_attribute(collaborator_attribute))],
                value=cst.Call(func=cst.Name(new_class_name)),
            )
        ]
    )


def _first_relevant_init_statement(statements: Sequence[cst.BaseStatement], requested: set[str]) -> int:
    for index, statement in enumerate(statements):
        assigned = {name for name, _annotation in _direct_self_assignment(statement)}
        visitor = _SelfAttributeVisitor()
        statement.visit(visitor)
        if requested & (assigned | visitor.names):
            return index

    if statements and _is_docstring_statement(statements[0]):
        return 1
    return 0


class ExtractClassTransformer(cst.CSTTransformer):
    """Move selected members of one top-level class into a collaborator."""

    def __init__(
        self,
        source_class: str,
        new_class_name: str,
        members: list[str],
        collaborator_attribute: str,
    ) -> None:
        super().__init__()
        self._source_class = source_class
        self._new_class_name = new_class_name
        self._members = members
        self._collaborator_attribute = collaborator_attribute
        self.class_found = False

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:  # noqa: N802
        source_classes = [
            statement
            for statement in updated_node.body
            if isinstance(statement, cst.ClassDef) and statement.name.value == self._source_class
        ]
        if not source_classes:
            return updated_node
        if len(source_classes) != 1:
            raise BackendError(f"Expected exactly one top-level class named {self._source_class!r}")
        self.class_found = True

        bindings = _module_binding_names(updated_node)
        if self._new_class_name in bindings:
            raise BackendError(f"Cannot create class {self._new_class_name!r}: module binding already exists")

        source = source_classes[0]
        replacement = self._extract(source)
        new_body: list[cst.BaseStatement] = []
        for statement in updated_node.body:
            if statement is source:
                new_body.extend(replacement)
            else:
                new_body.append(statement)
        return updated_node.with_changes(body=new_body)

    def _extract(self, source: cst.ClassDef) -> list[cst.BaseStatement]:
        if source.decorators:
            raise BackendError("extract_class does not support decorated source classes")
        if not isinstance(source.body, cst.IndentedBlock):
            raise BackendError("extract_class does not support one-line class bodies")

        methods: dict[str, list[cst.FunctionDef]] = {}
        constructors: list[cst.FunctionDef] = []
        direct_member_names: set[str] = set()
        for statement in source.body.body:
            if isinstance(statement, cst.FunctionDef):
                direct_member_names.add(statement.name.value)
                if statement.name.value == "__init__":
                    constructors.append(statement)
                else:
                    methods.setdefault(statement.name.value, []).append(statement)
            elif isinstance(statement, cst.SimpleStatementLine):
                for small in statement.body:
                    if isinstance(small, cst.Assign):
                        direct_member_names.update(
                            target.target.value for target in small.targets if isinstance(target.target, cst.Name)
                        )
                    elif isinstance(small, cst.AnnAssign) and isinstance(small.target, cst.Name):
                        direct_member_names.add(small.target.value)

        if "__slots__" in direct_member_names:
            raise BackendError("extract_class does not support classes declaring __slots__")
        if len(constructors) != 1:
            raise BackendError("extract_class requires exactly one __init__ method")
        constructor = constructors[0]
        if constructor.decorators or constructor.asynchronous is not None:
            raise BackendError("extract_class requires a plain synchronous __init__ method")
        if not isinstance(constructor.body, cst.IndentedBlock):
            raise BackendError("extract_class does not support one-line __init__ bodies")

        self_visitor = _SelfAttributeVisitor()
        source.body.visit(self_visitor)
        if self._collaborator_attribute in direct_member_names or self._collaborator_attribute in self_visitor.names:
            raise BackendError(
                f"Cannot use collaborator attribute {self._collaborator_attribute!r}: member already exists"
            )

        fields_by_name: dict[str, list[cst.Annotation | None]] = {}
        for statement in constructor.body.body:
            for name, annotation in _direct_self_assignment(statement):
                fields_by_name.setdefault(name, []).append(annotation)

        selected_fields: list[_FieldPlan] = []
        selected_methods: list[cst.FunctionDef] = []
        requested = set(self._members)
        for name in self._members:
            field_matches = fields_by_name.get(name, [])
            method_matches = methods.get(name, [])
            if field_matches and method_matches:
                raise BackendError(f"Cannot extract ambiguous member {name!r}: both field and method exist")
            if len(field_matches) > 1:
                raise BackendError(f"Cannot extract field {name!r}: constructor assigns it more than once")
            if len(method_matches) > 1:
                raise BackendError(f"Cannot extract method {name!r}: class defines it more than once")
            if field_matches:
                if name in direct_member_names:
                    raise BackendError(f"Cannot extract field {name!r}: a direct class member uses the same name")
                selected_fields.append(_FieldPlan(name=name, annotation=field_matches[0]))
            elif method_matches:
                selected_methods.append(method_matches[0])
            else:
                raise BackendError(
                    f"Member {name!r} is not a direct constructor field or instance method of {self._source_class!r}"
                )

        for method in selected_methods:
            if method.name.value.startswith("__") and method.name.value.endswith("__"):
                raise BackendError(f"Cannot extract special method {method.name.value!r}")
            if method.decorators or method.asynchronous is not None:
                raise BackendError(
                    f"Cannot extract method {method.name.value!r}: decorated and async methods are unsupported"
                )
            _forward_arguments(method)
            safety = _MovedMethodSafetyVisitor()
            method.body.visit(safety)
            unavailable = safety.names - requested
            if unavailable:
                raise BackendError(
                    f"Cannot extract method {method.name.value!r}: it uses unselected self member(s) "
                    f"{sorted(unavailable)}"
                )
            if safety.uses_bare_self:
                raise BackendError(f"Cannot extract method {method.name.value!r}: it passes or returns self")
            if safety.uses_super:
                raise BackendError(f"Cannot extract method {method.name.value!r}: it calls super()")
            if safety.yields:
                raise BackendError(f"Cannot extract generator method {method.name.value!r}")

        field_names = {field.name for field in selected_fields}
        insertion_index = _first_relevant_init_statement(constructor.body.body, requested)
        new_constructor_body: list[cst.BaseStatement] = []
        for index, statement in enumerate(constructor.body.body):
            if index == insertion_index:
                new_constructor_body.append(
                    _collaborator_assignment(self._new_class_name, self._collaborator_attribute)
                )
            new_constructor_body.append(
                _replace_selected_field_assignments(
                    statement,
                    field_names,
                    self._collaborator_attribute,
                )
            )
        if insertion_index == len(constructor.body.body):
            new_constructor_body.append(_collaborator_assignment(self._new_class_name, self._collaborator_attribute))
        new_constructor = constructor.with_changes(body=constructor.body.with_changes(body=new_constructor_body))

        source_body: list[cst.BaseStatement] = []
        for statement in source.body.body:
            if statement is constructor:
                source_body.append(new_constructor)
                for field in selected_fields:
                    source_body.extend(_field_properties(field, self._collaborator_attribute))
            elif isinstance(statement, cst.FunctionDef) and statement in selected_methods:
                source_body.append(_delegate_method(statement, self._collaborator_attribute))
            else:
                source_body.append(statement)

        collaborator_body: list[cst.BaseStatement] = list(selected_methods)
        if not collaborator_body:
            collaborator_body.append(cst.SimpleStatementLine(body=[cst.Pass()]))
        collaborator = cst.ClassDef(
            name=cst.Name(self._new_class_name),
            body=cst.IndentedBlock(body=collaborator_body),
        )
        modified_source = source.with_changes(body=source.body.with_changes(body=source_body))
        return [collaborator, modified_source]


async def extract_class(
    pyright: PyrightLSPClient,
    file_path: str,
    class_name: str,
    new_class_name: str,
    members: list[str],
    collaborator_attribute: str,
    apply: bool = False,
) -> RefactorResult:
    """Move selected fields and methods into a delegated collaborator class."""
    if not members:
        raise BackendError("extract_class requires at least one member")
    if len(set(members)) != len(members):
        raise BackendError("extract_class member names must be unique")
    invalid_members = sorted(name for name in members if not _is_identifier(name))
    if invalid_members:
        raise BackendError(f"extract_class member names must be valid identifiers: {invalid_members}")
    if not _is_identifier(class_name):
        raise BackendError("class_name must be a valid identifier")
    if not _is_identifier(new_class_name):
        raise BackendError("new_class_name must be a valid identifier")
    if new_class_name == class_name:
        raise BackendError("new_class_name must differ from class_name")
    if not _is_identifier(collaborator_attribute):
        raise BackendError("collaborator_attribute must be a valid identifier")
    if collaborator_attribute in members:
        raise BackendError("collaborator_attribute must not also be an extracted member")

    transformer = ExtractClassTransformer(
        class_name,
        new_class_name,
        members,
        collaborator_attribute,
    )
    edits, files_affected = apply_cst_transformer(file_path, transformer, apply=apply)
    if not transformer.class_found:
        raise BackendError(f"Top-level class {class_name!r} not found in {file_path}")

    result = RefactorResult(
        edits=edits,
        files_affected=files_affected,
        description=(f"Extracted {len(members)} member(s) from {class_name} into collaborator {new_class_name}"),
        applied=bool(apply and edits),
    )
    if apply and edits:
        return await post_apply_diagnostics(pyright, result)
    return result


__all__ = ["extract_class"]
