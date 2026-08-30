"""Conservatively break runtime import cycles with ``TYPE_CHECKING`` guards.

The fixer operates only on top-level import statements that participate in a
runtime cycle and whose imported bindings are used exclusively in annotations.
Mixed annotation/runtime imports are left untouched. Affected annotations are
stringified unless the module already enables postponed annotation evaluation.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import libcst as cst
from libcst.metadata import CodeRange, MetadataWrapper, PositionProvider

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import ModuleDependency, RefactorResult
from python_refactor_mcp.tools.metrics.dependencies import get_module_dependencies
from python_refactor_mcp.util.cst_apply import apply_cst_transformer_batch, parse_module

from .helpers import post_apply_diagnostics

if TYPE_CHECKING:
    from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient


@dataclass(frozen=True, slots=True)
class _ImportPlan:
    """Stable identity for one top-level import considered by the fixer."""

    statement_index: int
    fingerprint: str
    bindings: frozenset[str]


@dataclass(frozen=True, slots=True)
class _BindingUsage:
    """Whether one imported binding is needed statically or at runtime."""

    annotation: bool = False
    runtime: bool = False


def _is_type_checking_guard(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Name)
        and node.id == "TYPE_CHECKING"
        or isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "typing"
        and node.attr == "TYPE_CHECKING"
    )


def _annotation_name_ids(tree: ast.AST) -> set[int]:
    roots: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            roots.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            roots.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            roots.append(node.annotation)
    return {
        id(node)
        for root in roots
        for node in ast.walk(root)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


class _UsageCollector(ast.NodeVisitor):
    """Classify name loads without mistaking static-only guards for runtime use."""

    def __init__(self, annotation_name_ids: set[int]) -> None:
        self._annotation_name_ids = annotation_name_ids
        self._type_checking_depth = 0
        self.annotation_names: set[str] = set()
        self.runtime_names: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        if not isinstance(node.ctx, ast.Load):
            return
        if id(node) in self._annotation_name_ids or self._type_checking_depth:
            self.annotation_names.add(node.id)
        else:
            self.runtime_names.add(node.id)

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        self.visit(node.test)
        if _is_type_checking_guard(node.test):
            self._type_checking_depth += 1
            for statement in node.body:
                self.visit(statement)
            self._type_checking_depth -= 1
            for statement in node.orelse:
                self.visit(statement)
            return
        for statement in (*node.body, *node.orelse):
            self.visit(statement)


def _exported_names(tree: ast.Module) -> set[str]:
    """Return literal names published through a simple module ``__all__``."""
    exported: set[str] = set()
    for statement in tree.body:
        value: ast.expr | None = None
        if (
            isinstance(statement, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__all__"
                for target in statement.targets
            )
        ) or (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "__all__"
        ):
            value = statement.value
        if value is not None:
            exported.update(
                node.value
                for node in ast.walk(value)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            )
    return exported


def _binding_usage(source: str) -> tuple[ast.Module, dict[str, _BindingUsage]]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise BackendError(f"Cannot classify circular-import usages: {exc.msg}") from exc
    collector = _UsageCollector(_annotation_name_ids(tree))
    collector.visit(tree)
    runtime_names = collector.runtime_names | _exported_names(tree)
    names = collector.annotation_names | runtime_names
    return (
        tree,
        {
            name: _BindingUsage(
                annotation=name in collector.annotation_names,
                runtime=name in runtime_names,
            )
            for name in names
        },
    )


def _import_binding(alias: cst.ImportAlias, *, from_import: bool) -> str:
    if alias.asname is not None:
        if not isinstance(alias.asname.name, cst.Name):
            raise BackendError("Circular-import fixing does not support non-name aliases")
        return alias.asname.name.value
    if isinstance(alias.name, cst.Name):
        return alias.name.value
    dotted = cst.Module([]).code_for_node(alias.name)
    return dotted if from_import else dotted.split(".", 1)[0]


def _statement_bindings(statement: cst.BaseStatement) -> frozenset[str]:
    if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
        return frozenset()
    small = statement.body[0]
    if isinstance(small, cst.Import):
        return frozenset(_import_binding(alias, from_import=False) for alias in small.names)
    if isinstance(small, cst.ImportFrom) and not isinstance(small.names, cst.ImportStar):
        return frozenset(_import_binding(alias, from_import=True) for alias in small.names)
    return frozenset()


def _candidate_plans(source: str, file_path: str, cycle_lines: set[int]) -> tuple[_ImportPlan, ...]:
    module = parse_module(source, file_path)
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(PositionProvider)
    plans: list[_ImportPlan] = []
    for index, statement in enumerate(module.body):
        code_range = positions.get(statement)
        if not isinstance(code_range, CodeRange) or code_range.start.line - 1 not in cycle_lines:
            continue
        bindings = _statement_bindings(statement)
        if not bindings:
            continue
        plans.append(
            _ImportPlan(
                statement_index=index,
                fingerprint=module.code_for_node(statement).strip(),
                bindings=bindings,
            )
        )
    return tuple(plans)


def _has_future_annotations(tree: ast.Module) -> bool:
    return any(
        isinstance(statement, ast.ImportFrom)
        and statement.module == "__future__"
        and any(alias.name == "annotations" for alias in statement.names)
        for statement in tree.body
    )


def _has_type_checking_import(tree: ast.Module) -> bool:
    return any(
        isinstance(statement, ast.ImportFrom)
        and statement.module == "typing"
        and any(
            alias.name == "TYPE_CHECKING" and (alias.asname is None or alias.asname == "TYPE_CHECKING")
            for alias in statement.names
        )
        for statement in tree.body
    )


def _top_level_bindings(tree: ast.Module) -> set[str]:
    bindings: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bindings.add(statement.name)
        elif isinstance(statement, ast.Assign):
            bindings.update(target.id for target in statement.targets if isinstance(target, ast.Name))
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            bindings.add(statement.target.id)
        elif isinstance(statement, ast.Import):
            bindings.update(alias.asname or alias.name.split(".", 1)[0] for alias in statement.names)
        elif isinstance(statement, ast.ImportFrom):
            bindings.update(alias.asname or alias.name for alias in statement.names if alias.name != "*")
    return bindings


def _annotation_uses(annotation: cst.BaseExpression, bindings: frozenset[str]) -> bool:
    source = cst.Module([]).code_for_node(annotation)
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError:
        return False
    return any(
        isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id in bindings
        for node in ast.walk(tree)
    )


class _StringifyAnnotations(cst.CSTTransformer):
    def __init__(self, bindings: frozenset[str]) -> None:
        self._bindings = bindings

    def leave_Annotation(  # noqa: N802
        self,
        original_node: cst.Annotation,
        updated_node: cst.Annotation,
    ) -> cst.Annotation:
        expression = updated_node.annotation
        if isinstance(expression, cst.SimpleString) or not _annotation_uses(
            expression, self._bindings
        ):
            return updated_node
        source = cst.Module([]).code_for_node(expression)
        return updated_node.with_changes(annotation=cst.SimpleString(repr(source)))


def _is_type_checking_block(statement: cst.BaseStatement) -> bool:
    return (
        isinstance(statement, cst.If)
        and isinstance(statement.test, cst.Name)
        and statement.test.value == "TYPE_CHECKING"
    )


def _import_insert_index(body: Sequence[cst.BaseStatement]) -> int:
    index = 0
    if body and isinstance(body[0], cst.SimpleStatementLine):
        first = body[0].body
        if len(first) == 1 and isinstance(first[0], cst.Expr) and isinstance(
            first[0].value, cst.SimpleString
        ):
            index = 1
    while index < len(body):
        statement = body[index]
        if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
            break
        small = statement.body[0]
        if not (
            isinstance(small, cst.ImportFrom)
            and isinstance(small.module, cst.Name)
            and small.module.value == "__future__"
        ):
            break
        index += 1
    return index


def _type_checking_block_index(body: Sequence[cst.BaseStatement]) -> int:
    index = _import_insert_index(body)
    while index < len(body):
        statement = body[index]
        if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
            break
        if not isinstance(statement.body[0], (cst.Import, cst.ImportFrom)):
            break
        index += 1
    return index


class FixCircularImportsTransformer(cst.CSTTransformer):
    """Move preselected imports only when current usages remain type-only."""

    def __init__(self, plans: tuple[_ImportPlan, ...]) -> None:
        self._plans = plans
        self.moved_count = 0

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:  # noqa: N802
        source = updated_node.code
        tree, usages = _binding_usage(source)
        selected_indexes: set[int] = set()
        moved_bindings: set[str] = set()
        for plan in self._plans:
            if plan.statement_index >= len(updated_node.body):
                raise BackendError("Circular-import source changed after dependency analysis")
            statement = updated_node.body[plan.statement_index]
            fingerprint = updated_node.code_for_node(statement).strip()
            if fingerprint != plan.fingerprint or _statement_bindings(statement) != plan.bindings:
                raise BackendError("Circular-import source changed after dependency analysis")
            if all(
                usages.get(binding, _BindingUsage()).annotation
                and not usages.get(binding, _BindingUsage()).runtime
                for binding in plan.bindings
            ):
                selected_indexes.add(plan.statement_index)
                moved_bindings.update(plan.bindings)

        if not selected_indexes:
            return updated_node
        if not _has_type_checking_import(tree) and "TYPE_CHECKING" in _top_level_bindings(tree):
            raise BackendError("Cannot add TYPE_CHECKING guard because that name is already bound")

        rewritten = updated_node
        frozen_bindings = frozenset(moved_bindings)
        if not _has_future_annotations(tree):
            rewritten = updated_node.visit(_StringifyAnnotations(frozen_bindings))

        moved = [rewritten.body[index] for index in sorted(selected_indexes)]
        body = [
            statement
            for index, statement in enumerate(rewritten.body)
            if index not in selected_indexes
        ]

        if not _has_type_checking_import(tree):
            body.insert(
                _import_insert_index(body),
                cst.SimpleStatementLine(
                    body=[
                        cst.ImportFrom(
                            module=cst.Name("typing"),
                            names=[cst.ImportAlias(name=cst.Name("TYPE_CHECKING"))],
                        )
                    ]
                ),
            )

        existing_index = next(
            (index for index, statement in enumerate(body) if _is_type_checking_block(statement)),
            None,
        )
        if existing_index is not None:
            existing = body[existing_index]
            if not isinstance(existing, cst.If) or not isinstance(existing.body, cst.IndentedBlock):
                raise BackendError("Existing TYPE_CHECKING guard must use an indented block")
            body[existing_index] = existing.with_changes(
                body=existing.body.with_changes(body=[*moved, *existing.body.body])
            )
        else:
            body.insert(
                _type_checking_block_index(body),
                cst.If(
                    test=cst.Name("TYPE_CHECKING"),
                    body=cst.IndentedBlock(body=moved),
                    leading_lines=[cst.EmptyLine()],
                ),
            )

        self.moved_count = len(moved)
        return rewritten.with_changes(body=body)


def _cycle_lines_by_source(
    dependencies: list[ModuleDependency],
    cycles: list[list[str]],
) -> dict[str, set[int]]:
    component_by_file = {
        file_path: frozenset(component)
        for component in cycles
        for file_path in component
    }
    result: dict[str, set[int]] = {}
    for dependency in dependencies:
        component = component_by_file.get(dependency.source)
        if component is not None and dependency.target in component:
            result.setdefault(dependency.source, set()).add(dependency.line)
    return result


async def fix_circular_imports(
    pyright: PyrightLSPClient,
    config: ServerConfig,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Hoist provably annotation-only imports out of runtime dependency cycles."""
    if file_path is not None and file_paths:
        raise BackendError("Provide file_path or file_paths, not both")

    graph = await get_module_dependencies(config)
    if graph.scan_failures:
        raise BackendError(
            "Cannot safely fix circular imports while dependency scanning has "
            f"{len(graph.scan_failures)} failure(s)"
        )
    cycle_lines = _cycle_lines_by_source(graph.dependencies, graph.circular_dependencies)
    requested = (
        {str(Path(path).resolve()) for path in file_paths}
        if file_paths
        else {str(Path(file_path).resolve())}
        if file_path is not None
        else None
    )
    candidate_paths = sorted(
        path for path in cycle_lines if requested is None or path in requested
    )

    plans_by_path: dict[str, tuple[_ImportPlan, ...]] = {}
    for path in candidate_paths:
        try:
            source = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise BackendError("Cannot read a circular-import candidate") from exc
        plans = _candidate_plans(source, path, cycle_lines[path])
        if plans:
            plans_by_path[path] = plans

    transformers: dict[str, FixCircularImportsTransformer] = {}

    def transformer_factory(path: str) -> cst.CSTTransformer:
        transformer = FixCircularImportsTransformer(plans_by_path[path])
        transformers[path] = transformer
        return transformer

    edits, files_affected = apply_cst_transformer_batch(
        sorted(plans_by_path),
        transformer_factory,
        apply=apply,
    )
    moved_count = sum(transformer.moved_count for transformer in transformers.values())
    result = RefactorResult(
        edits=edits,
        files_affected=files_affected,
        description=(
            f"Moved {moved_count} annotation-only circular import statement(s) "
            "behind TYPE_CHECKING; mixed and runtime imports were left unchanged"
        ),
        applied=bool(apply and edits),
    )
    if apply and edits:
        return await post_apply_diagnostics(pyright, result)
    return result


__all__ = ["fix_circular_imports"]
