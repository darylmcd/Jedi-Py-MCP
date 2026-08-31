"""Shared fail-closed source-shape checks for semantic converters."""

from __future__ import annotations

import libcst as cst

from python_refactor_mcp.errors import BackendError

_MUTABLE_DEFAULT_CONSTRUCTORS = frozenset({"bytearray", "dict", "list", "set"})


class _CommentFinder(cst.CSTVisitor):
    """Record whether a subtree contains comments that a rewrite could lose."""

    def __init__(self) -> None:
        self.found = False

    def visit_Comment(self, node: cst.Comment) -> None:  # noqa: N802
        self.found = True


def contains_comment(node: cst.CSTNode) -> bool:
    """Return whether ``node`` contains a concrete syntax comment."""
    finder = _CommentFinder()
    node.visit(finder)
    return finder.found


def top_level_class(module: cst.Module, class_name: str) -> cst.ClassDef:
    """Resolve exactly one top-level class without matching nested classes."""
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


def is_mutable_default(value: cst.BaseExpression | None) -> bool:
    """Return whether a default is a mutable built-in container expression."""
    if isinstance(value, (cst.Dict, cst.DictComp, cst.List, cst.ListComp, cst.Set, cst.SetComp)):
        return True
    return (
        isinstance(value, cst.Call)
        and isinstance(value.func, cst.Name)
        and value.func.value in _MUTABLE_DEFAULT_CONSTRUCTORS
    )


__all__ = ["contains_comment", "is_mutable_default", "top_level_class"]
