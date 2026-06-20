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


def _rolled_back_result(
    normalized: list[tuple[str, dict[str, Any]]],
    step_meta: list[dict[str, Any]],
    failed_index: int,
    error: str,
) -> TransactionResult:
    """Build the structured result for a rolled-back execution failure.

    Steps before ``failed_index`` were applied then reverted (``rolled_back``);
    the step at ``failed_index`` is the abort point (``failed`` with ``error``
    populated); every step after it never ran (``skipped``). Disk has already
    been restored to the pre-transaction state by the backend, so no diffs are
    reported.
    """
    steps: list[TransactionStepResult] = []
    for index, (tool, _args) in enumerate(normalized):
        if index < failed_index:
            meta = step_meta[index]
            steps.append(
                TransactionStepResult(
                    index=index,
                    tool=tool,
                    status="rolled_back",
                    files_affected=meta["files_affected"],
                    edit_count=meta["edit_count"],
                )
            )
        elif index == failed_index:
            steps.append(
                TransactionStepResult(index=index, tool=tool, status="failed", error=error)
            )
        else:
            steps.append(TransactionStepResult(index=index, tool=tool, status="skipped"))

    failed_tool = normalized[failed_index][0]
    return TransactionResult(
        applied=False,
        rolled_back=True,
        steps=steps,
        files_affected=[],
        description=(
            f"Transaction aborted at step {failed_index} ('{failed_tool}') and rolled back: {error}"
        ),
        diffs=[],
    )


async def refactor_transaction(rope: RopeBackend, steps: list[dict[str, Any]]) -> TransactionResult:
    """Apply an ordered ``(tool, args)`` list atomically under one change stack.

    Two clearly-different failure modes:

    * **Input / pre-flight errors RAISE.** An empty step list, a structurally
      malformed step (no string ``tool`` / non-object ``args`` / missing
      ``file_path``), or a step naming an unsupported tool is rejected *before*
      any change is pushed — :class:`RopeError` propagates (→ ``ValueError`` at
      the tool boundary) with nothing applied. All steps' tool-names and arg
      shape are validated up front so an unknown tool in a later step is caught
      before the first step runs.
    * **Execution failures RETURN a rolled-back result.** Once execution begins,
      if a step's refactoring raises mid-sequence or an overlap is detected, the
      backend reverts every pushed change and this function RETURNS a
      :class:`TransactionResult` with ``applied=False``, ``rolled_back=True``,
      the already-completed steps marked ``rolled_back``, the failing step
      ``failed`` with its ``error`` populated, and the remaining steps
      ``skipped``. Disk is left byte-identical to the pre-transaction state.

    On success: ``applied=True``, every step ``applied`` with a merged unified
    diff summary.
    """
    normalized = _normalize_steps(steps)
    # Pre-flight: reject unsupported tools / missing file_path across ALL steps
    # before any edit is pushed. Raises RopeError on bad input.
    rope.validate_transaction_steps(normalized)

    # Snapshot originals before any edit so the post-commit diff summary can be
    # built against the pre-transaction state.
    target_files = _collect_target_files(normalized)
    originals: dict[str, str] = {}
    for file_path in target_files:
        try:
            originals[file_path] = Path(file_path).read_text(encoding="utf-8")
        except OSError:
            originals[file_path] = ""

    outcome = await rope.apply_transaction(normalized)
    step_meta: list[dict[str, Any]] = outcome["step_meta"]

    if not outcome["committed"]:
        # Execution failure: disk has already been rolled back by the backend.
        # Surface a structured result rather than raising.
        return _rolled_back_result(
            normalized, step_meta, outcome["failed_index"], outcome["error"]
        )

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
