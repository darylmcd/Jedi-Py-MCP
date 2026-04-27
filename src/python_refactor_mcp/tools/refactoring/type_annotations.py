"""Materialize Pyright-inferred type hints into real source-level annotations.

The MCP tool ``apply_type_annotations`` walks Pyright's inlay-hint results for
each target file, filters to type hints (kind ``"type"`` — return-type and
parameter/variable annotations), and emits zero-width insertion ``TextEdit``s at
each hint's position. This closes the loop with ``get_inlay_hints`` (read) and
``get_type_coverage`` (measure) that already exist on the server.

Why this does NOT use the CST foundation: Pyright already returns precise
insertion positions with the annotation text pre-formatted (including
``padding_left``/``padding_right`` flags). Walking the CST to re-derive these
positions would add complexity without correctness benefit. CST-based tools
like ``convert_to_dataclass`` / ``extract_class`` legitimately need
``util/cst_apply.py``; this one does not.
"""

from __future__ import annotations

from pathlib import Path

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import (
    InlayHint,
    Range,
    RefactorResult,
    TextEdit,
)
from python_refactor_mcp.tools.refactoring.helpers import (
    PyrightRefactoringBackend,
    post_apply_diagnostics,
    result_from_text_edits,
)
from python_refactor_mcp.util.shared import end_position_for_content


def _hint_to_edit(file_path: str, hint: InlayHint) -> TextEdit:
    """Translate a Pyright inlay hint into a zero-width insertion ``TextEdit``."""
    insert = hint.label
    if hint.padding_left:
        insert = " " + insert
    if hint.padding_right:
        insert = insert + " "
    return TextEdit(
        file_path=file_path,
        range=Range(start=hint.position, end=hint.position),
        new_text=insert,
    )


async def _hints_for_file(
    pyright: PyrightRefactoringBackend,
    file_path: str,
) -> list[InlayHint]:
    """Fetch inlay hints across the whole file, filtered to type hints."""
    try:
        source = Path(file_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise BackendError(f"Cannot read file for type annotation: {exc}") from exc

    end = end_position_for_content(source)
    hints = await pyright.get_inlay_hints(file_path, 0, 0, end.line, end.character)
    return [hint for hint in hints if hint.kind == "type"]


async def apply_type_annotations(
    pyright: PyrightRefactoringBackend,
    file_path: str,
    apply: bool = False,
    file_paths: list[str] | None = None,
) -> RefactorResult:
    """Materialize Pyright-inferred type hints into real source annotations.

    Pulls type-kind inlay hints across each target file and emits a zero-width
    insertion ``TextEdit`` at each hint position, with ``padding_left`` /
    ``padding_right`` honored. Defaults to preview mode; ``apply=True`` writes
    edits atomically and refreshes Pyright diagnostics for the changed files.

    Files where Pyright surfaces no type hints are silently dropped — they
    contribute nothing to ``edits`` or ``files_affected``.
    """
    targets = file_paths if file_paths is not None else [file_path]

    edits: list[TextEdit] = []
    for fp in targets:
        for hint in await _hints_for_file(pyright, fp):
            edits.append(_hint_to_edit(fp, hint))

    if not edits:
        return RefactorResult(
            edits=[],
            files_affected=[],
            description="No inferable type annotations found",
            applied=False,
        )

    description = f"Applied {len(edits)} type annotation(s) across {len({e.file_path for e in edits})} file(s)"
    result = result_from_text_edits(edits, description, apply)
    if apply:
        return await post_apply_diagnostics(pyright, result)
    return result


# Helper so tests can construct synthetic hints without importing Position/Range each time.
__all__ = ["apply_type_annotations"]
