"""Rename-related refactoring tools."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from python_refactor_mcp.models import DiffPreview, PrepareRenameResult, RefactorResult
from python_refactor_mcp.util.diff import build_unified_diff

from .helpers import (
    PyrightRefactoringBackend,
    RopeRefactoringBackend,
    post_apply_diagnostics,
)


async def ensure_renameable(
    pyright: PyrightRefactoringBackend,
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
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    new_name: str,
    apply: bool = False,
    include_diff: bool = False,
) -> RefactorResult:
    """Rename a symbol at the provided position."""
    await ensure_renameable(pyright, file_path, line, character)
    result = await rope.rename(file_path, line, character, new_name, apply)
    result = await post_apply_diagnostics(pyright, result)

    if include_diff and not result.applied and result.edits:
        # Group edits by file and build diffs.
        edits_by_file: dict[str, list] = defaultdict(list)
        for edit in result.edits:
            edits_by_file[edit.file_path].append(edit)
        diffs: list[DiffPreview] = []
        for fp, file_edits in sorted(edits_by_file.items()):
            diff_text = build_unified_diff(fp, file_edits)
            if diff_text:
                diffs.append(DiffPreview(file_path=fp, unified_diff=diff_text))
        result.diffs = diffs

    return result


async def prepare_rename(
    pyright: PyrightRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
) -> PrepareRenameResult | None:
    """Run rename preflight checks for the requested source position."""
    return await pyright.prepare_rename(file_path, line, character)
