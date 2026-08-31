"""Shared LibCST import-binding and insertion planning helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import libcst as cst
from libcst.metadata import GlobalScope, MetadataWrapper, ScopeProvider

from python_refactor_mcp.errors import BackendError


def import_alias_binding(alias: cst.ImportAlias, *, from_import: bool) -> str:
    """Return the top-level name introduced by one import alias."""
    if alias.asname is not None:
        if not isinstance(alias.asname.name, cst.Name):
            raise BackendError("Unsupported non-name import alias")
        return alias.asname.name.value
    dotted = cst.Module([]).code_for_node(alias.name)
    return dotted if from_import else dotted.split(".", 1)[0]


def top_level_bindings(module: cst.Module) -> set[str]:
    """Return names assigned in the module scope, including nested control flow."""
    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    scope = wrapper.resolve(ScopeProvider)[module]
    if not isinstance(scope, GlobalScope):  # pragma: no cover - Module always owns GlobalScope
        raise BackendError("Cannot resolve module-level bindings")
    bindings = {assignment.name for assignment in scope.assignments}
    for statement in module.body:
        if not isinstance(statement, cst.SimpleStatementLine):
            break
        for small in statement.body:
            if (
                not isinstance(small, cst.ImportFrom)
                or not _is_future_import(small)
                or isinstance(small.names, cst.ImportStar)
            ):
                continue
            bindings.difference_update(import_alias_binding(alias, from_import=True) for alias in small.names)
    return bindings


def statement_bindings(statement: cst.BaseStatement) -> set[str]:
    """Return module-scope names assigned or deleted by one top-level statement."""
    module_statement = cast(cst.SimpleStatementLine | cst.BaseCompoundStatement, statement)
    module = cst.Module(body=[module_statement])
    bindings = top_level_bindings(module)
    deletion_collector = _TopLevelDeletionCollector()
    statement.visit(deletion_collector)
    bindings.update(deletion_collector.names)
    return bindings


def reserve_unique_binding(
    bindings: set[str],
    preferred: str,
    fallback: str,
) -> str:
    """Reserve and return a collision-free binding name."""
    if preferred not in bindings:
        bindings.add(preferred)
        return preferred

    candidate = fallback
    suffix = 2
    while candidate in bindings:
        candidate = f"{fallback}_{suffix}"
        suffix += 1
    bindings.add(candidate)
    return candidate


def import_insertion_index(
    body: Sequence[cst.BaseStatement],
    *,
    after_import_block: bool = False,
) -> int:
    """Find an insertion point after the docstring/futures or full import block."""
    index = 1 if body and _is_docstring(body[0]) else 0
    while index < len(body):
        statement = body[index]
        if not isinstance(statement, cst.SimpleStatementLine) or not statement.body:
            break
        if after_import_block:
            is_allowed = all(isinstance(small, (cst.Import, cst.ImportFrom)) for small in statement.body)
        else:
            is_allowed = all(_is_future_import(small) for small in statement.body)
        if not is_allowed:
            break
        index += 1
    return index


def _is_docstring(statement: cst.BaseStatement) -> bool:
    if not isinstance(statement, cst.SimpleStatementLine) or len(statement.body) != 1:
        return False
    expression = statement.body[0]
    return isinstance(expression, cst.Expr) and isinstance(expression.value, cst.SimpleString)


def _is_future_import(statement: cst.BaseSmallStatement) -> bool:
    return (
        isinstance(statement, cst.ImportFrom)
        and isinstance(statement.module, cst.Name)
        and statement.module.value == "__future__"
    )


class _TopLevelDeletionCollector(cst.CSTVisitor):
    """Collect simple-name deletes without descending into nested scopes."""

    def __init__(self) -> None:
        self.names: set[str] = set()

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:  # noqa: N802
        return False

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:  # noqa: N802
        return False

    def visit_Lambda(self, node: cst.Lambda) -> bool:  # noqa: N802
        return False

    def visit_Del(self, node: cst.Del) -> None:  # noqa: N802
        if isinstance(node.target, cst.Name):
            self.names.add(node.target.value)


__all__ = [
    "import_alias_binding",
    "import_insertion_index",
    "reserve_unique_binding",
    "statement_bindings",
    "top_level_bindings",
]
