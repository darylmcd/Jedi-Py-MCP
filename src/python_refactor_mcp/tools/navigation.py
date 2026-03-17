"""Navigation tools orchestrating symbol lookup and call graph queries."""

from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable
from typing import Protocol

from python_refactor_mcp.models import CallHierarchyItem, CallHierarchyResult, Location

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


class _JediNavigationBackend(Protocol):
    """Protocol describing Jedi navigation methods used by this module."""

    async def goto_definition(self, file_path: str, line: int, character: int) -> list[Location]:
        """Return definition locations using Jedi."""
        ...


def _call_item_key(item: CallHierarchyItem) -> tuple[str, int, int, str]:
    """Build a stable key for call hierarchy deduplication."""
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


async def _traverse_calls(
    root: CallHierarchyItem,
    depth: int,
    fetch_next: Callable[[CallHierarchyItem], Awaitable[list[CallHierarchyItem]]],
) -> list[CallHierarchyItem]:
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
            pending.append((next_item, current_depth + 1))

    return sorted(discovered.values(), key=_call_item_key)


async def call_hierarchy(
    pyright: _PyrightNavigationBackend,
    file_path: str,
    line: int,
    character: int,
    direction: str = "both",
    depth: int = 1,
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
        return CallHierarchyResult(item=placeholder, callers=[], callees=[])

    root = roots[0]
    callers: list[CallHierarchyItem] = []
    callees: list[CallHierarchyItem] = []

    if normalized_direction in {"callers", "both"}:
        callers = await _traverse_calls(root, depth, pyright.get_incoming_calls)

    if normalized_direction in {"callees", "both"}:
        callees = await _traverse_calls(root, depth, pyright.get_outgoing_calls)

    return CallHierarchyResult(item=root, callers=callers, callees=callees)


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
