"""Refactoring tools orchestrating rope edits with Pyright validation."""

from __future__ import annotations

from typing import Protocol

from python_refactor_mcp.models import Diagnostic, RefactorResult


class _PyrightRefactoringBackend(Protocol):
    """Protocol describing Pyright methods used in apply validation paths."""

    async def notify_file_changed(self, file_path: str) -> None:
        """Notify backend that file contents changed on disk."""
        ...

    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]:
        """Return diagnostics for one file or the full workspace."""
        ...


class _RopeRefactoringBackend(Protocol):
    """Protocol describing rope refactoring methods used by this module."""

    async def rename(
        self,
        file_path: str,
        line: int,
        character: int,
        new_name: str,
        apply: bool,
    ) -> RefactorResult:
        """Rename symbol and return computed edits/result."""
        ...

    async def extract_method(
        self,
        file_path: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        method_name: str,
        apply: bool,
    ) -> RefactorResult:
        """Extract selected code into a method."""
        ...

    async def extract_variable(
        self,
        file_path: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        variable_name: str,
        apply: bool,
    ) -> RefactorResult:
        """Extract selected code into a variable."""
        ...

    async def inline(self, file_path: str, line: int, character: int, apply: bool) -> RefactorResult:
        """Inline symbol and return computed edits/result."""
        ...

    async def move(
        self,
        source_file: str,
        symbol_name: str,
        destination_file: str,
        apply: bool,
    ) -> RefactorResult:
        """Move symbol and return computed edits/result."""
        ...


def _diagnostic_key(item: Diagnostic) -> tuple[str, int, int, int, int, str, str]:
    """Build a stable key for diagnostic deduplication and ordering."""
    return (
        item.file_path,
        item.range.start.line,
        item.range.start.character,
        item.range.end.line,
        item.range.end.character,
        item.severity,
        item.message,
    )


async def _attach_post_apply_diagnostics(
    pyright: _PyrightRefactoringBackend,
    result: RefactorResult,
) -> RefactorResult:
    """Notify Pyright of changed files and append refreshed diagnostics."""
    if not result.applied:
        return result

    normalized_files = sorted({file_path for file_path in result.files_affected})
    for file_path in normalized_files:
        await pyright.notify_file_changed(file_path)

    diagnostics: dict[tuple[str, int, int, int, int, str, str], Diagnostic] = {}
    for file_path in normalized_files:
        file_diagnostics = await pyright.get_diagnostics(file_path)
        for diagnostic in file_diagnostics:
            diagnostics[_diagnostic_key(diagnostic)] = diagnostic

    result.diagnostics_after = sorted(diagnostics.values(), key=_diagnostic_key)
    return result


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
    result = await rope.rename(file_path, line, character, new_name, apply)
    return await _attach_post_apply_diagnostics(pyright, result)


async def extract_method(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    start_line: int,
    start_character: int,
    end_line: int,
    end_character: int,
    method_name: str,
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


async def move_symbol(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    source_file: str,
    symbol_name: str,
    destination_file: str,
    apply: bool = False,
) -> RefactorResult:
    """Move a symbol from one file to another."""
    result = await rope.move(source_file, symbol_name, destination_file, apply)
    return await _attach_post_apply_diagnostics(pyright, result)
