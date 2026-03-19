"""Composite tools that coordinate multiple backends in one workflow."""

from __future__ import annotations

from typing import Protocol

from python_refactor_mcp.models import Diagnostic, DiffPreview, Location, RefactorResult, TextEdit
from python_refactor_mcp.util.diff import build_unified_diff


class _PyrightCompositeBackend(Protocol):
    """Protocol describing Pyright methods used by composite tools."""

    async def get_references(
        self,
        file_path: str,
        line: int,
        char: int,
        include_declaration: bool,
    ) -> list[Location]:
        """Return references for a source position."""
        ...

    async def notify_file_changed(self, file_path: str) -> None:
        """Notify backend that file contents changed on disk."""
        ...

    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]:
        """Return diagnostics for one file or whole workspace."""
        ...


class _RopeCompositeBackend(Protocol):
    """Protocol describing rope methods used by composite tools."""

    async def rename(
        self,
        file_path: str,
        line: int,
        character: int,
        new_name: str,
        apply: bool,
    ) -> RefactorResult:
        """Rename symbol and return computed edits/result."""
        ...


def _diagnostic_key(item: Diagnostic) -> tuple[str, int, int, int, int, str, str]:
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


async def _attach_post_apply_diagnostics(
    pyright: _PyrightCompositeBackend,
    result: RefactorResult,
) -> RefactorResult:
    """Notify Pyright of changed files and append refreshed diagnostics."""
    if not result.applied:
        return result

    normalized_files = sorted({file_path for file_path in result.files_affected})
    for changed_file in normalized_files:
        await pyright.notify_file_changed(changed_file)

    diagnostics: dict[tuple[str, int, int, int, int, str, str], Diagnostic] = {}
    for changed_file in normalized_files:
        file_diagnostics = await pyright.get_diagnostics(changed_file)
        for diagnostic in file_diagnostics:
            diagnostics[_diagnostic_key(diagnostic)] = diagnostic

    result.diagnostics_after = sorted(diagnostics.values(), key=_diagnostic_key)
    return result


async def smart_rename(
    pyright: _PyrightCompositeBackend,
    rope: _RopeCompositeBackend,
    file_path: str,
    line: int,
    character: int,
    new_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Coordinate analysis and refactoring for a safe rename."""
    _ = await pyright.get_references(file_path, line, character, True)
    result = await rope.rename(file_path, line, character, new_name, apply)
    return await _attach_post_apply_diagnostics(pyright, result)


async def diff_preview(edits: list[TextEdit]) -> list[DiffPreview]:
    """Build unified diff previews for one or more text edits."""
    edits_by_file: dict[str, list[TextEdit]] = {}
    for edit in edits:
        edits_by_file.setdefault(edit.file_path, []).append(edit)

    previews = [
        DiffPreview(file_path=file_path, unified_diff=build_unified_diff(file_path, file_edits))
        for file_path, file_edits in sorted(edits_by_file.items())
    ]
    return previews
