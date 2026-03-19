"""Navigation tools orchestrating symbol lookup and call/type hierarchy queries."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    CallHierarchyItem,
    CallHierarchyResult,
    FoldingRange,
    Location,
    Position,
    SelectionRangeResult,
    SymbolOutlineItem,
    TypeHierarchyItem,
    TypeHierarchyResult,
)

_VALID_DIRECTIONS = {"callers", "callees", "both"}


class _PyrightNavigationBackend(Protocol):
    """Protocol describing Pyright navigation methods used by this module."""

    async def prepare_call_hierarchy(
        self,
        file_path: str,
        line: int,
        char: int,
    ) -> list[CallHierarchyItem]:
        """Prepare call hierarchy item(s) for traversal."""
        ...

    async def get_incoming_calls(self, item: CallHierarchyItem) -> list[CallHierarchyItem]:
        """Return direct callers of a hierarchy item."""
        ...

    async def get_outgoing_calls(self, item: CallHierarchyItem) -> list[CallHierarchyItem]:
        """Return direct callees of a hierarchy item."""
        ...

    async def get_definition(self, file_path: str, line: int, char: int) -> list[Location]:
        """Return definition locations for a source position."""
        ...

    async def get_document_symbols(self, file_path: str) -> list[SymbolOutlineItem]:
        """Return document symbols for a file."""
        ...

    async def get_implementation(self, file_path: str, line: int, char: int) -> list[Location]:
        """Return implementation locations for a source position."""
        ...

    async def get_declaration(self, file_path: str, line: int, char: int) -> list[Location]:
        """Return declaration locations for a source position."""
        ...

    async def get_type_definition(self, file_path: str, line: int, char: int) -> list[Location]:
        """Return type definition locations for a source position."""
        ...

    async def get_folding_ranges(self, file_path: str) -> list[FoldingRange]:
        """Return foldable source ranges for a file."""
        ...

    async def prepare_type_hierarchy(self, file_path: str, line: int, char: int) -> list[TypeHierarchyItem]:
        """Prepare type hierarchy item(s) for traversal."""
        ...

    async def get_supertypes(self, item: TypeHierarchyItem) -> list[TypeHierarchyItem]:
        """Return direct supertypes of a hierarchy item."""
        ...

    async def get_subtypes(self, item: TypeHierarchyItem) -> list[TypeHierarchyItem]:
        """Return direct subtypes of a hierarchy item."""
        ...

    async def get_selection_range(self, file_path: str, positions: list[Position]) -> list[SelectionRangeResult]:
        """Return nested selection ranges for one or more positions."""
        ...


class _JediNavigationBackend(Protocol):
    """Protocol describing Jedi navigation methods used by this module."""

    async def goto_definition(self, file_path: str, line: int, character: int) -> list[Location]:
        """Return definition locations using Jedi."""
        ...


def _call_item_key(item: CallHierarchyItem) -> tuple[str, int, int, str]:
    """Build a stable key for call hierarchy deduplication."""
    return (item.file_path, item.range.start.line, item.range.start.character, item.name)


def _type_item_key(item: TypeHierarchyItem) -> tuple[str, int, int, str]:
    """Build a stable key for type hierarchy deduplication."""
    return (item.file_path, item.range.start.line, item.range.start.character, item.name)


def _location_key(location: Location) -> tuple[str, int, int, int, int]:
    """Build a stable key for location deduplication and sorting."""
    return (
        location.file_path,
        location.range.start.line,
        location.range.start.character,
        location.range.end.line,
        location.range.end.character,
    )


def _outline_key(item: SymbolOutlineItem) -> tuple[str, int, int, str]:
    """Build a stable sort key for outline items."""
    return (item.file_path, item.selection_range.start.line, item.selection_range.start.character, item.name)


def _apply_limit[T](items: list[T], limit: int | None) -> tuple[list[T], bool]:
    """Apply an optional positive limit and return items plus truncated flag."""
    if limit is None:
        return items, False
    if limit < 1:
        raise ValueError("limit must be greater than or equal to 1")
    if len(items) <= limit:
        return items, False
    return items[:limit], True


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
) -> TypeHierarchyResult:
    """Get incoming and outgoing type hierarchy data."""
    normalized_direction = direction.strip().lower()
    if normalized_direction not in _VALID_DIRECTIONS:
        valid = ", ".join(sorted(_VALID_DIRECTIONS))
        raise ValueError(f"Invalid direction '{direction}'. Expected one of: {valid}")
    if depth < 1:
        raise ValueError("depth must be greater than or equal to 1")

    roots = await pyright.prepare_type_hierarchy(file_path, line, character)
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

    if normalized_direction in {"callers", "both"}:
        supertypes, super_truncated = await _traverse_types(root, depth, pyright.get_supertypes, max_items)
        truncated = truncated or super_truncated

    if normalized_direction in {"callees", "both"}:
        subtypes, sub_truncated = await _traverse_types(root, depth, pyright.get_subtypes, max_items)
        truncated = truncated or sub_truncated

    return TypeHierarchyResult(item=root, supertypes=supertypes, subtypes=subtypes, truncated=truncated)


async def selection_range(
    pyright: _PyrightNavigationBackend,
    file_path: str,
    positions: list[Position],
) -> list[SelectionRangeResult]:
    """Return nested selection ranges for one or more source positions."""
    if not positions:
        raise ValueError("positions must contain at least one position")
    return await pyright.get_selection_range(file_path, positions)


async def goto_definition(
    pyright: _PyrightNavigationBackend,
    jedi: _JediNavigationBackend,
    file_path: str,
    line: int,
    character: int,
) -> list[Location]:
    """Navigate to symbol definitions from a source position."""
    pyright_locations = await pyright.get_definition(file_path, line, character)
    if pyright_locations:
        deduped = {
            _location_key(location): location
            for location in pyright_locations
        }
        return sorted(deduped.values(), key=_location_key)

    jedi_locations = await jedi.goto_definition(file_path, line, character)
    deduped_jedi = {
        _location_key(location): location
        for location in jedi_locations
    }
    return sorted(deduped_jedi.values(), key=_location_key)


async def get_symbol_outline(
    pyright: _PyrightNavigationBackend,
    config: ServerConfig,
    file_path: str | None = None,
    kind_filter: list[str] | None = None,
    name_pattern: str | None = None,
    limit: int | None = None,
) -> list[SymbolOutlineItem]:
    """Return a filtered symbol outline for one file or the full workspace."""
    candidate_files = (
        [Path(file_path).resolve()]
        if file_path is not None
        else sorted(config.workspace_root.rglob("*.py"))
    )

    normalized_kinds = {kind.strip().lower() for kind in kind_filter} if kind_filter else None
    compiled_pattern = re.compile(name_pattern) if name_pattern else None

    outlines: list[SymbolOutlineItem] = []
    for path in candidate_files:
        if not path.is_file():
            continue
        for item in await pyright.get_document_symbols(str(path)):
            if normalized_kinds is not None and item.kind.strip().lower() not in normalized_kinds:
                continue
            if compiled_pattern is not None and compiled_pattern.search(item.name) is None:
                continue
            outlines.append(item)

    sorted_items = sorted(outlines, key=_outline_key)
    limited, _ = _apply_limit(sorted_items, limit)
    return limited


async def find_implementations(
    pyright: _PyrightNavigationBackend,
    file_path: str,
    line: int,
    character: int,
) -> list[Location]:
    """Find implementation locations for the symbol at the provided position."""
    implementations = await pyright.get_implementation(file_path, line, character)
    deduped = {
        _location_key(location): location
        for location in implementations
    }
    return sorted(deduped.values(), key=_location_key)


async def get_declaration(
    pyright: _PyrightNavigationBackend,
    file_path: str,
    line: int,
    character: int,
) -> list[Location]:
    """Navigate to symbol declarations from a source position."""
    declarations = await pyright.get_declaration(file_path, line, character)
    deduped = {
        _location_key(location): location
        for location in declarations
    }
    return sorted(deduped.values(), key=_location_key)


async def get_type_definition(
    pyright: _PyrightNavigationBackend,
    file_path: str,
    line: int,
    character: int,
) -> list[Location]:
    """Navigate to symbol type definitions from a source position."""
    definitions = await pyright.get_type_definition(file_path, line, character)
    deduped = {
        _location_key(location): location
        for location in definitions
    }
    return sorted(deduped.values(), key=_location_key)


async def get_folding_ranges(
    pyright: _PyrightNavigationBackend,
    file_path: str,
) -> list[FoldingRange]:
    """Return foldable ranges for a file in deterministic order."""
    ranges = await pyright.get_folding_ranges(file_path)
    return sorted(ranges, key=lambda item: (item.start_line, item.end_line, item.kind or ""))
