"""Rename-related refactoring tools."""

from __future__ import annotations

from pathlib import Path

from python_refactor_mcp.models import PrepareRenameResult, RefactorResult

from .helpers import (
    _attach_post_apply_diagnostics,
    _PyrightRefactoringBackend,
    _RopeRefactoringBackend,
)


async def _ensure_renameable(
    pyright: _PyrightRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
) -> None:
    """Validate renameability before invoking rope operations."""
    preflight = await pyright.prepare_rename(file_path, line, character)
    if preflight is not None:
        return

    # Pyright can return null for valid positions in some dynamic contexts.
    # Keep a lightweight local guard for obvious invalid targets.
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


async def rename_symbol(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    new_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Rename a symbol at the provided position."""
    await _ensure_renameable(pyright, file_path, line, character)
    result = await rope.rename(file_path, line, character, new_name, apply)
    return await _attach_post_apply_diagnostics(pyright, result)


async def prepare_rename(
    pyright: _PyrightRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
) -> PrepareRenameResult | None:
    """Run rename preflight checks for the requested source position."""
    return await pyright.prepare_rename(file_path, line, character)
