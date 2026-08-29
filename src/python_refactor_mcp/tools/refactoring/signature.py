"""Signature change, parameter introduction, and restructure tools."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from python_refactor_mcp.models import RefactorResult, SignatureOperation, TextEdit

from .helpers import post_apply_diagnostics
from .rename import ensure_renameable
from .signature_annotations import restore_signature_metadata

if TYPE_CHECKING:
    from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient
    from python_refactor_mcp.backends.rope_backend import RopeBackend


async def change_signature(
    pyright: PyrightLSPClient,
    rope: RopeBackend,
    file_path: str,
    line: int,
    character: int,
    operations: list[SignatureOperation],
    apply: bool = False,
) -> RefactorResult:
    """Apply ordered signature operations and update call sites.

    rope re-emits the parameter list without type annotations on several
    operations; a LibCST post-pass re-attaches the dropped annotations on the
    definition before the edits are written. rope runs in preview; the
    corrected edits are applied (with rollback) only when ``apply`` is set.
    """
    await ensure_renameable(pyright, file_path, line, character)
    result = await rope.change_signature(file_path, line, character, operations, False)

    target = str(Path(file_path).resolve())
    corrected: list[TextEdit] = []
    for edit in result.edits:
        if str(Path(edit.file_path).resolve()) == target:
            # Lazily read the original only when there is a definition-file edit.
            original_src = Path(edit.file_path).read_text(encoding="utf-8")
            fixed_text = restore_signature_metadata(original_src, edit.new_text, line, character, operations)
            corrected.append(edit.model_copy(update={"new_text": fixed_text}) if fixed_text != edit.new_text else edit)
        else:
            corrected.append(edit)

    files_affected = sorted({edit.file_path for edit in corrected})
    if apply and corrected:
        rope.apply_edits(corrected)
    final = RefactorResult(
        edits=corrected,
        files_affected=files_affected,
        description=result.description,
        applied=apply and bool(corrected),
    )
    return await post_apply_diagnostics(pyright, final)


async def introduce_parameter(
    pyright: PyrightLSPClient,
    rope: RopeBackend,
    file_path: str,
    line: int,
    character: int,
    parameter_name: str,
    default_value: str,
    apply: bool = False,
) -> RefactorResult:
    """Introduce a parameter and optionally apply edits on disk."""
    result = await rope.introduce_parameter(
        file_path,
        line,
        character,
        parameter_name,
        default_value,
        apply,
    )
    return await post_apply_diagnostics(pyright, result)


async def restructure(
    pyright: PyrightLSPClient,
    rope: RopeBackend,
    pattern: str,
    goal: str,
    checks: dict[str, str] | None = None,
    imports: list[str] | None = None,
    file_path: str | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Run Rope restructure (structural replace) with optional scope filters."""
    result = await rope.restructure(pattern, goal, checks, imports, file_path, apply)
    return await post_apply_diagnostics(pyright, result)
