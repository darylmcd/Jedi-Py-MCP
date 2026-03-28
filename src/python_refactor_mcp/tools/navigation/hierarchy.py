"""Call hierarchy and type hierarchy navigation tools."""

from __future__ import annotations

import ast
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path

from python_refactor_mcp.models import (
    CallHierarchyItem,
    CallHierarchyResult,
    TypeHierarchyItem,
    TypeHierarchyResult,
)

from ._protocols import _PyrightNavigationBackend

_VALID_DIRECTIONS = {"callers", "callees", "both"}

# Type hierarchy uses its own direction vocabulary with backward-compat aliases.
_VALID_TYPE_DIRECTIONS = {"supertypes", "subtypes", "both"}
_TYPE_DIRECTION_ALIASES: dict[str, str] = {"callers": "supertypes", "callees": "subtypes"}


def _call_item_key(item: CallHierarchyItem) -> tuple[str, int, int, str]:
    """Build a stable key for call hierarchy deduplication."""
    return (item.file_path, item.range.start.line, item.range.start.character, item.name)


def _type_item_key(item: TypeHierarchyItem) -> tuple[str, int, int, str]:
    """Build a stable key for type hierarchy deduplication."""
    return (item.file_path, item.range.start.line, item.range.start.character, item.name)


async def _traverse_calls(
    root: CallHierarchyItem,
    depth: int,
    fetch_next: Callable[[CallHierarchyItem], Awaitable[list[CallHierarchyItem]]],
    max_items: int | None,
) -> tuple[list[CallHierarchyItem], bool]:
    """Traverse call hierarchy breadth-first up to the requested depth."""
    visited: set[tuple[str, int, int, str]] = {_call_item_key(root)}
    discovered: dict[tuple[str, int, int, str], CallHierarchyItem] = {}
    pending: deque[tuple[CallHierarchyItem, int]] = deque([(root, 0)])

    while pending:
        current, current_depth = pending.popleft()
        if current_depth >= depth:
            continue

        next_items = await fetch_next(current)
        for next_item in next_items:
            key = _call_item_key(next_item)
            if key in visited:
                continue
            visited.add(key)
            discovered[key] = next_item
            if max_items is not None and len(discovered) >= max_items:
                return sorted(discovered.values(), key=_call_item_key), True
            pending.append((next_item, current_depth + 1))

    return sorted(discovered.values(), key=_call_item_key), False


async def _traverse_types(
    root: TypeHierarchyItem,
    depth: int,
    fetch_next: Callable[[TypeHierarchyItem], Awaitable[list[TypeHierarchyItem]]],
    max_items: int | None,
) -> tuple[list[TypeHierarchyItem], bool]:
    """Traverse type hierarchy breadth-first up to the requested depth."""
    visited: set[tuple[str, int, int, str]] = {_type_item_key(root)}
    discovered: dict[tuple[str, int, int, str], TypeHierarchyItem] = {}
    pending: deque[tuple[TypeHierarchyItem, int]] = deque([(root, 0)])

    while pending:
        current, current_depth = pending.popleft()
        if current_depth >= depth:
            continue

        next_items = await fetch_next(current)
        for next_item in next_items:
            key = _type_item_key(next_item)
            if key in visited:
                continue
            visited.add(key)
            discovered[key] = next_item
            if max_items is not None and len(discovered) >= max_items:
                return sorted(discovered.values(), key=_type_item_key), True
            pending.append((next_item, current_depth + 1))

    return sorted(discovered.values(), key=_type_item_key), False


def _resolve_class_position(
    file_path: str,
    line: int,
    character: int,
    class_name: str | None,
) -> tuple[int, int] | None:
    """Find the exact class-name token position via AST when Pyright needs precise cursor placement."""
    try:
        source = Path(file_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return None

    source_lines = source.splitlines()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        # Match by class_name if provided, otherwise by proximity to the requested line.
        if class_name is not None:
            if node.name != class_name:
                continue
        elif abs((node.lineno - 1) - line) > 2:
            continue

        name_line = node.lineno - 1
        if name_line < 0 or name_line >= len(source_lines):
            continue
        line_text = source_lines[name_line]
        # Find the column of the class name identifier on its definition line.
        name_col = line_text.find(node.name, node.col_offset)
        if name_col < 0:
            name_col = node.col_offset
        return (name_line, name_col)

    return None


async def call_hierarchy(
    pyright: _PyrightNavigationBackend,
    file_path: str,
    line: int,
    character: int,
    direction: str = "both",
    depth: int = 1,
    max_items: int | None = 200,
) -> CallHierarchyResult:
    """Get incoming and outgoing call hierarchy data."""
    normalized_direction = direction.strip().lower()
    if normalized_direction not in _VALID_DIRECTIONS:
        valid = ", ".join(sorted(_VALID_DIRECTIONS))
        raise ValueError(f"Invalid direction '{direction}'. Expected one of: {valid}")
    if depth < 1:
        raise ValueError("depth must be greater than or equal to 1")

    roots = await pyright.prepare_call_hierarchy(file_path, line, character)

    # Decorator detection: if the resolved root points outside the workspace
    # (e.g., stdlib contextlib.py or site-packages), the cursor likely landed on
    # a decorator.  Retry targeting the `def` keyword of the actual function.
    if roots:
        root_file = roots[0].file_path
        try:
            resolved_root = Path(root_file).resolve()
            is_external = "site-packages" in str(resolved_root) or resolved_root != Path(file_path).resolve()
            if is_external and str(resolved_root) != str(Path(file_path).resolve()):
                # Find the actual def line via AST
                source = Path(file_path).read_text(encoding="utf-8")
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Match by line proximity: decorator_list precedes the def
                        node_line = node.lineno - 1
                        decorator_lines = [d.lineno - 1 for d in node.decorator_list] if node.decorator_list else []
                        if line == node_line or line in decorator_lines:
                            # Retry at the def keyword position (col_offset of the function name)
                            retry_line = node.lineno - 1
                            source_lines = source.splitlines()
                            retry_col = node.col_offset
                            if retry_line < len(source_lines):
                                name_idx = source_lines[retry_line].find(node.name, node.col_offset)
                                if name_idx >= 0:
                                    retry_col = name_idx
                            new_roots = await pyright.prepare_call_hierarchy(file_path, retry_line, retry_col)
                            if new_roots:
                                roots = new_roots
                            break
        except (OSError, SyntaxError):
            pass  # Keep original roots on any failure.

    if not roots:
        placeholder = CallHierarchyItem.model_validate(
            {
                "name": "",
                "kind": "function",
                "file_path": file_path,
                "range": {
                    "start": {"line": line, "character": character},
                    "end": {"line": line, "character": character},
                },
            }
        )
        return CallHierarchyResult(item=placeholder, callers=[], callees=[], truncated=False)

    root = roots[0]
    callers: list[CallHierarchyItem] = []
    callees: list[CallHierarchyItem] = []
    truncated = False

    if normalized_direction in {"callers", "both"}:
        callers, callers_truncated = await _traverse_calls(root, depth, pyright.get_incoming_calls, max_items)
        truncated = truncated or callers_truncated

    if normalized_direction in {"callees", "both"}:
        callees, callees_truncated = await _traverse_calls(root, depth, pyright.get_outgoing_calls, max_items)
        truncated = truncated or callees_truncated

    return CallHierarchyResult(item=root, callers=callers, callees=callees, truncated=truncated)


async def type_hierarchy(
    pyright: _PyrightNavigationBackend,
    file_path: str,
    line: int,
    character: int,
    direction: str = "both",
    depth: int = 3,
    max_items: int | None = 200,
    class_name: str | None = None,
) -> TypeHierarchyResult:
    """Get incoming and outgoing type hierarchy data."""
    normalized_direction = _TYPE_DIRECTION_ALIASES.get(
        direction.strip().lower(), direction.strip().lower()
    )
    if normalized_direction not in _VALID_TYPE_DIRECTIONS:
        valid = ", ".join(sorted(_VALID_TYPE_DIRECTIONS))
        raise ValueError(f"Invalid direction '{direction}'. Expected one of: {valid}")
    if depth < 1:
        raise ValueError("depth must be greater than or equal to 1")

    roots = await pyright.prepare_type_hierarchy(file_path, line, character)

    # Retry with AST-resolved class name position when Pyright returns empty
    # (cursor may be on the `class` keyword instead of the name token).
    if not roots:
        resolved = _resolve_class_position(file_path, line, character, class_name)
        if resolved and (resolved[0] != line or resolved[1] != character):
            roots = await pyright.prepare_type_hierarchy(file_path, resolved[0], resolved[1])

    if not roots:
        placeholder = TypeHierarchyItem.model_validate(
            {
                "name": "",
                "kind": "class",
                "file_path": file_path,
                "range": {
                    "start": {"line": line, "character": character},
                    "end": {"line": line, "character": character},
                },
            }
        )
        return TypeHierarchyResult(item=placeholder, supertypes=[], subtypes=[], truncated=False)

    root = roots[0]
    supertypes: list[TypeHierarchyItem] = []
    subtypes: list[TypeHierarchyItem] = []
    truncated = False

    if normalized_direction in {"supertypes", "both"}:
        supertypes, super_truncated = await _traverse_types(root, depth, pyright.get_supertypes, max_items)
        truncated = truncated or super_truncated

    if normalized_direction in {"subtypes", "both"}:
        subtypes, sub_truncated = await _traverse_types(root, depth, pyright.get_subtypes, max_items)
        truncated = truncated or sub_truncated

    return TypeHierarchyResult(item=root, supertypes=supertypes, subtypes=subtypes, truncated=truncated)
