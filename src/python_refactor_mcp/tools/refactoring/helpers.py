"""Shared helpers for refactoring submodules.

The hand-maintained ``PyrightRefactoringBackend`` and ``RopeRefactoringBackend``
protocols that lived here historically were structural duplicates of the
concrete ``PyrightLSPClient`` and ``RopeBackend`` classes — every signature
change had to be made in two places. Call sites now depend on the concrete
classes directly via ``TYPE_CHECKING`` imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from python_refactor_mcp.models import (
    Position,
    Range,
    RefactorResult,
    TextEdit,
)
from python_refactor_mcp.util.diff import apply_text_edits_atomically
from python_refactor_mcp.util.paths import uri_to_path
from python_refactor_mcp.util.shared import attach_post_apply_diagnostics

if TYPE_CHECKING:
    from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient


def range_contains_position(range_value: Range, line: int, character: int) -> bool:
    """Return whether a 0-based position is inside a diagnostic range."""
    start = (range_value.start.line, range_value.start.character)
    end = (range_value.end.line, range_value.end.character)
    target = (line, character)
    return start <= target <= end


def full_file_range(file_path: str) -> Range:
    """Build a range covering the entire current file content."""
    from python_refactor_mcp.errors import RopeError  # noqa: PLC0415
    from python_refactor_mcp.util.shared import end_position_for_content  # noqa: PLC0415

    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise RopeError(f"Cannot read file for range computation: {exc}") from exc
    return Range(start=Position(line=0, character=0), end=end_position_for_content(content))


def workspace_edit_to_text_edits(workspace_edit: object) -> list[TextEdit]:
    """Convert an LSP workspace edit payload into project TextEdit models."""
    if not isinstance(workspace_edit, dict):
        return []

    edits: list[TextEdit] = []
    changes = workspace_edit.get("changes")
    if isinstance(changes, dict):
        for uri, file_edits in changes.items():
            if not isinstance(uri, str) or not isinstance(file_edits, list):
                continue
            file_path = uri_to_path(uri)
            for edit in file_edits:
                if not isinstance(edit, dict):
                    continue
                range_value = edit.get("range")
                new_text = edit.get("newText")
                if not isinstance(range_value, dict) or not isinstance(new_text, str):
                    continue
                edits.append(TextEdit(file_path=file_path, range=Range.model_validate(range_value), new_text=new_text))

    document_changes = workspace_edit.get("documentChanges")
    if isinstance(document_changes, list):
        for change in document_changes:
            if not isinstance(change, dict):
                continue
            text_document = change.get("textDocument")
            edits_value = change.get("edits")
            if not isinstance(text_document, dict) or not isinstance(edits_value, list):
                continue
            uri = text_document.get("uri")
            if not isinstance(uri, str):
                continue
            file_path = uri_to_path(uri)
            for edit in edits_value:
                if not isinstance(edit, dict):
                    continue
                range_value = edit.get("range")
                new_text = edit.get("newText")
                if not isinstance(range_value, dict) or not isinstance(new_text, str):
                    continue
                edits.append(TextEdit(file_path=file_path, range=Range.model_validate(range_value), new_text=new_text))

    deduped: dict[tuple[str, int, int, int, int, str], TextEdit] = {}
    for edit in edits:
        key = (
            edit.file_path,
            edit.range.start.line,
            edit.range.start.character,
            edit.range.end.line,
            edit.range.end.character,
            edit.new_text,
        )
        deduped[key] = edit
    return sorted(
        deduped.values(),
        key=lambda item: (
            item.file_path,
            item.range.start.line,
            item.range.start.character,
            item.range.end.line,
            item.range.end.character,
        ),
    )


def result_from_text_edits(edits: list[TextEdit], description: str, apply: bool) -> RefactorResult:
    """Build a refactor result from LSP-style text edits and optionally apply them."""
    files_affected = sorted({edit.file_path for edit in edits})
    if not apply:
        return RefactorResult(edits=edits, files_affected=files_affected, description=description, applied=False)

    apply_text_edits_atomically(edits)

    return RefactorResult(edits=edits, files_affected=files_affected, description=description, applied=True)


async def post_apply_diagnostics(
    pyright: PyrightLSPClient,
    result: RefactorResult,
) -> RefactorResult:
    """Notify Pyright of changed files and append refreshed diagnostics."""
    return await attach_post_apply_diagnostics(pyright, result)
