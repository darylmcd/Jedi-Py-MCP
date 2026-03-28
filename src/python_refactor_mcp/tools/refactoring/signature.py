"""Signature change, parameter introduction, and restructure tools."""

from __future__ import annotations

from python_refactor_mcp.models import RefactorResult, SignatureOperation

from .helpers import (
    _attach_post_apply_diagnostics,
    _PyrightRefactoringBackend,
    _RopeRefactoringBackend,
)
from .rename import _ensure_renameable


async def change_signature(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    operations: list[SignatureOperation],
    apply: bool = False,
) -> RefactorResult:
    """Apply ordered signature operations and update call sites."""
    await _ensure_renameable(pyright, file_path, line, character)
    result = await rope.change_signature(file_path, line, character, operations, apply)
    return await _attach_post_apply_diagnostics(pyright, result)


async def introduce_parameter(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
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
    return await _attach_post_apply_diagnostics(pyright, result)


async def restructure(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    pattern: str,
    goal: str,
    checks: dict[str, str] | None = None,
    imports: list[str] | None = None,
    file_path: str | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Run Rope restructure (structural replace) with optional scope filters."""
    result = await rope.restructure(pattern, goal, checks, imports, file_path, apply)
    return await _attach_post_apply_diagnostics(pyright, result)
