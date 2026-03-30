"""Shared helpers used by multiple tool and backend modules."""

from __future__ import annotations

import keyword
from pathlib import Path
from typing import Protocol

from python_refactor_mcp.models import Diagnostic, Location, Position


class DiagnosticsNotifier(Protocol):
    """Protocol for backends that supply diagnostics and file change notifications."""

    async def notify_file_changed(self, file_path: str) -> None:
        """Notify backend that file contents changed on disk."""
        ...

    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]:
        """Return diagnostics for one file or the full workspace."""
        ...


def apply_limit[T](items: list[T], limit: int | None) -> tuple[list[T], bool]:
    """Apply an optional positive limit and return items plus truncated flag.

    Returns ``(items, False)`` when *limit* is ``None`` or the list is within
    bounds.  Returns ``(items[:limit], True)`` when truncation is required.
    """
    if limit is None:
        return items, False
    if limit < 1:
        raise ValueError("limit must be greater than or equal to 1")
    if len(items) <= limit:
        return items, False
    return items[:limit], True


def location_key(location: Location) -> tuple[str, int, int, int, int]:
    """Build a stable key for location deduplication and sorting."""
    return (
        location.file_path,
        location.range.start.line,
        location.range.start.character,
        location.range.end.line,
        location.range.end.character,
    )


def diagnostic_key(item: Diagnostic) -> tuple[str, int, int, int, int, str, str]:
    """Build a stable key for diagnostic deduplication and ordering."""
    return (
        item.file_path,
        item.range.start.line,
        item.range.start.character,
        item.range.end.line,
        item.range.end.character,
        item.severity,
        item.message,
    )


async def attach_post_apply_diagnostics(
    pyright: DiagnosticsNotifier,
    result: object,
) -> object:
    """Notify Pyright of changed files and append refreshed diagnostics.

    Operates on any object with ``applied``, ``files_affected``, and
    ``diagnostics_after`` attributes (i.e. ``RefactorResult``).
    """
    from python_refactor_mcp.models import RefactorResult  # noqa: PLC0415

    if not isinstance(result, RefactorResult) or not result.applied:
        return result

    normalized_files = sorted(set(result.files_affected))
    for file_path in normalized_files:
        await pyright.notify_file_changed(file_path)

    diagnostics: dict[tuple[str, int, int, int, int, str, str], Diagnostic] = {}
    for file_path in normalized_files:
        file_diagnostics = await pyright.get_diagnostics(file_path)
        for diagnostic in file_diagnostics:
            diagnostics[diagnostic_key(diagnostic)] = diagnostic

    result.diagnostics_after = sorted(diagnostics.values(), key=diagnostic_key)
    return result


def end_position_for_content(content: str) -> Position:
    """Compute the end position of an entire file content string.

    Shared helper used by rope_backend and refactoring helpers.
    """
    if not content:
        return Position(line=0, character=0)
    lines = content.splitlines()
    if not lines:
        return Position(line=0, character=0)
    if content.endswith(("\n", "\r")):
        return Position(line=len(lines), character=0)
    return Position(line=len(lines) - 1, character=len(lines[-1]))


def validate_identifier(name: str, param_label: str) -> str:
    """Validate that *name* is a legal Python identifier and not a keyword.

    Returns *name* unchanged.  Raises ``ValueError`` on failure.
    """
    if not name.isidentifier():
        raise ValueError(f"'{name}' is not a valid Python identifier (parameter: {param_label})")
    if keyword.iskeyword(name):
        raise ValueError(f"'{name}' is a Python keyword and cannot be used as an identifier (parameter: {param_label})")
    return name


def validate_workspace_path(file_path: str, workspace_root: Path) -> str:
    """Resolve *file_path* and verify it is under *workspace_root*.

    Returns the resolved absolute path string.  Raises ``ValueError`` if the
    path is outside the workspace boundary.
    """
    resolved = Path(file_path).resolve()
    try:
        resolved.relative_to(workspace_root.resolve())
    except ValueError as exc:
        raise ValueError(
            f"File path is outside the workspace root: {resolved} is not under {workspace_root}"
        ) from exc
    return str(resolved)
