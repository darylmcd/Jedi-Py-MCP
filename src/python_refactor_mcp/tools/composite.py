"""Composite tools that coordinate multiple backends in one workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from python_refactor_mcp.models import Diagnostic, DiffPreview, Location, RefactorResult, TextEdit
from python_refactor_mcp.util.diff import build_unified_diff
from python_refactor_mcp.util.shared import attach_post_apply_diagnostics


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

    async def prepare_rename(self, file_path: str, line: int, char: int) -> object | None:
        """Run rename preflight and return metadata when rename is valid."""
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


async def _attach_post_apply_diagnostics(
    pyright: _PyrightCompositeBackend,
    result: RefactorResult,
) -> RefactorResult:
    """Notify Pyright of changed files and append refreshed diagnostics."""
    return await attach_post_apply_diagnostics(pyright, result)  # type: ignore[return-value]


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
    preflight = await pyright.prepare_rename(file_path, line, character)
    if preflight is None:
        lines = Path(file_path).read_text(encoding="utf-8").splitlines()
        if line < 0 or line >= len(lines):
            raise ValueError("Rename preflight failed: line is outside file bounds.")
        line_text = lines[line]
        if character < 0 or character >= len(line_text):
            raise ValueError("Rename preflight failed: character is outside line bounds.")
        target = line_text[character]
        if not (target.isalnum() or target == "_"):
            raise ValueError(
                "Rename preflight failed for the selected position. "
                "Choose an identifier location and retry."
            )
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
