"""Composite tools that coordinate multiple backends in one workflow."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from python_refactor_mcp.errors import RopeError
from python_refactor_mcp.models import (
    DiffPreview,
    TextEdit,
    TransactionResult,
    TransactionStepResult,
)
from python_refactor_mcp.util.diff import build_unified_diff

if TYPE_CHECKING:
    from python_refactor_mcp.backends.rope_backend import RopeBackend


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


def _normalize_steps(steps: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Validate and normalize raw ``{"tool": ..., "args": {...}}`` step dicts.

    Returns ``(tool, args)`` tuples. Raises :class:`RopeError` for malformed
    steps so the failure surfaces structurally before any edit is applied.
    """
    if not steps:
        raise RopeError("refactor_transaction requires at least one step")

    normalized: list[tuple[str, dict[str, Any]]] = []
    for index, step in enumerate(steps):
        tool = step.get("tool")
        if not isinstance(tool, str) or not tool:
            raise RopeError(f"transaction step {index} is missing a string 'tool'")
        args = step.get("args", {})
        if not isinstance(args, dict):
            raise RopeError(f"transaction step {index} 'args' must be an object")
        normalized.append((tool, args))
    return normalized


def _collect_target_files(steps: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """Collect the distinct resolved file paths every step names via ``file_path``."""
    files: list[str] = []
    for _tool, args in steps:
        file_path = args.get("file_path")
        if isinstance(file_path, str):
            resolved = str(Path(file_path).resolve())
            if resolved not in files:
                files.append(resolved)
    return files


async def refactor_transaction(rope: RopeBackend, steps: list[dict[str, Any]]) -> TransactionResult:
    """Apply an ordered ``(tool, args)`` list atomically under one change stack.

    Each step previews against the running (partially-edited) source, is checked
    for overlap against earlier steps, then applied. Any failure — unsupported
    tool, a step that raises, or an overlap — rolls back the entire transaction
    so disk is left byte-identical to the pre-transaction state, and re-raises.
    """
    normalized = _normalize_steps(steps)

    # Snapshot originals before any edit so the post-commit diff summary can be
    # built against the pre-transaction state.
    target_files = _collect_target_files(normalized)
    originals: dict[str, str] = {}
    for file_path in target_files:
        try:
            originals[file_path] = Path(file_path).read_text(encoding="utf-8")
        except OSError:
            originals[file_path] = ""

    try:
        step_meta = await rope.apply_transaction(normalized)
    except RopeError as exc:
        # The backend has already rolled the change stack back; surface the
        # failing step and cause in a structured result via the exception.
        # Re-raise so the error boundary returns a structured tool error.
        raise RopeError(f"refactor_transaction aborted and rolled back: {exc}") from exc

    step_results = [
        TransactionStepResult(
            index=index,
            tool=meta["tool"],
            status="applied",
            files_affected=meta["files_affected"],
            edit_count=meta["edit_count"],
        )
        for index, meta in enumerate(step_meta)
    ]

    diffs: list[DiffPreview] = []
    for file_path in sorted(originals):
        before = originals[file_path]
        after = Path(file_path).read_text(encoding="utf-8")
        if before == after:
            continue
        diff_text = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=file_path,
                tofile=file_path,
            )
        )
        diffs.append(DiffPreview(file_path=file_path, unified_diff=diff_text))

    affected = sorted({fp for meta in step_meta for fp in meta["files_affected"]})
    return TransactionResult(
        applied=True,
        rolled_back=False,
        steps=step_results,
        files_affected=affected,
        description=f"Applied {len(step_results)} step(s) atomically",
        diffs=diffs,
    )
