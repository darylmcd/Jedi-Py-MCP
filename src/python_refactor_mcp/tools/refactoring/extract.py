"""Extract and inline refactoring tools."""

from __future__ import annotations

from python_refactor_mcp.models import RefactorResult

from .helpers import (
    _attach_post_apply_diagnostics,
    _PyrightRefactoringBackend,
    _RopeRefactoringBackend,
)


async def extract_method(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    start_line: int,
    start_character: int,
    end_line: int,
    end_character: int,
    method_name: str,
    similar: bool = False,
    apply: bool = False,
) -> RefactorResult:
    """Extract selected code into a method."""
    result = await rope.extract_method(
        file_path,
        start_line,
        start_character,
        end_line,
        end_character,
        method_name,
        similar,
        apply,
    )
    return await _attach_post_apply_diagnostics(pyright, result)


async def extract_variable(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    start_line: int,
    start_character: int,
    end_line: int,
    end_character: int,
    variable_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Extract selected expression into a variable."""
    result = await rope.extract_variable(
        file_path,
        start_line,
        start_character,
        end_line,
        end_character,
        variable_name,
        apply,
    )
    return await _attach_post_apply_diagnostics(pyright, result)


async def inline_variable(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Inline a variable at the provided position."""
    result = await rope.inline(file_path, line, character, apply)
    return await _attach_post_apply_diagnostics(pyright, result)


async def inline_method(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Inline a function/method body into all call sites and remove the original definition."""
    result = await rope.inline_method(file_path, line, character, apply)
    return await _attach_post_apply_diagnostics(pyright, result)


async def inline_parameter(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Remove a parameter by inlining its default value into the function body."""
    result = await rope.inline_parameter(file_path, line, character, apply)
    return await _attach_post_apply_diagnostics(pyright, result)
