"""Composite tools that coordinate multiple backends in one workflow."""

from __future__ import annotations

from python_refactor_mcp.models import DiffPreview, TextEdit
from python_refactor_mcp.util.diff import build_unified_diff


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
