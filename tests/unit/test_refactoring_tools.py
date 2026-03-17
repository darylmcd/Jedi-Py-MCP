"""Unit tests for refactoring tool delegation and apply validation paths."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.models import Diagnostic, Position, Range, RefactorResult, TextEdit
from python_refactor_mcp.tools import refactoring


def _edit(path: str) -> TextEdit:
    return TextEdit(
        file_path=path,
        range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
        new_text="x",
    )


def _diag(path: str, line: int) -> Diagnostic:
    return Diagnostic(
        file_path=path,
        range=Range(start=Position(line=line, character=0), end=Position(line=line, character=1)),
        severity="error",
        message=f"e{line}",
        code=None,
    )


@pytest.mark.asyncio
async def test_rename_symbol_delegates_to_rope_no_apply() -> None:
    """Ensure rename delegates arguments and skips diagnostics when not applied."""
    pyright = AsyncMock()
    rope = AsyncMock()
    rope.rename.return_value = RefactorResult(
        edits=[_edit("/repo/a.py")],
        files_affected=["/repo/a.py"],
        description="rename",
        applied=False,
    )

    result = await refactoring.rename_symbol(pyright, rope, "/repo/a.py", 1, 2, "new_name", apply=False)

    assert result.applied is False
    rope.rename.assert_awaited_once_with("/repo/a.py", 1, 2, "new_name", False)
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_symbol_apply_refreshes_diagnostics() -> None:
    """Ensure apply mode notifies Pyright and attaches refreshed diagnostics."""
    pyright = AsyncMock()
    rope = AsyncMock()

    rope.rename.return_value = RefactorResult(
        edits=[_edit("/repo/a.py"), _edit("/repo/b.py")],
        files_affected=["/repo/b.py", "/repo/a.py", "/repo/a.py"],
        description="rename",
        applied=True,
    )
    pyright.get_diagnostics.side_effect = [
        [_diag("/repo/a.py", 2), _diag("/repo/a.py", 1)],
        [_diag("/repo/b.py", 3)],
    ]

    result = await refactoring.rename_symbol(pyright, rope, "/repo/a.py", 1, 2, "new_name", apply=True)

    assert result.diagnostics_after is not None
    assert [item.file_path for item in result.diagnostics_after] == ["/repo/a.py", "/repo/a.py", "/repo/b.py"]
    pyright.notify_file_changed.assert_any_await("/repo/a.py")
    pyright.notify_file_changed.assert_any_await("/repo/b.py")


@pytest.mark.asyncio
async def test_extract_inline_and_move_delegate_correctly() -> None:
    """Ensure all remaining refactor tools delegate to rope backend."""
    pyright = AsyncMock()
    rope = AsyncMock()

    rope.extract_method.return_value = RefactorResult(edits=[], files_affected=[], description="x", applied=False)
    rope.extract_variable.return_value = RefactorResult(edits=[], files_affected=[], description="x", applied=False)
    rope.inline.return_value = RefactorResult(edits=[], files_affected=[], description="x", applied=False)
    rope.move.return_value = RefactorResult(edits=[], files_affected=[], description="x", applied=False)

    await refactoring.extract_method(pyright, rope, "/repo/a.py", 0, 0, 1, 1, "m", apply=False)
    await refactoring.extract_variable(pyright, rope, "/repo/a.py", 0, 0, 1, 1, "v", apply=False)
    await refactoring.inline_variable(pyright, rope, "/repo/a.py", 0, 0, apply=False)
    await refactoring.move_symbol(pyright, rope, "/repo/a.py", "Thing", "/repo/b.py", apply=False)

    rope.extract_method.assert_awaited_once_with("/repo/a.py", 0, 0, 1, 1, "m", False)
    rope.extract_variable.assert_awaited_once_with("/repo/a.py", 0, 0, 1, 1, "v", False)
    rope.inline.assert_awaited_once_with("/repo/a.py", 0, 0, False)
    rope.move.assert_awaited_once_with("/repo/a.py", "Thing", "/repo/b.py", False)
