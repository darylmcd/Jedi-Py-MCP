"""Unit tests for composite tool orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.models import Diagnostic, Position, Range, RefactorResult, TextEdit
from python_refactor_mcp.tools import composite
from tests.helpers import make_diag as _diag, make_edit as _edit


@pytest.mark.asyncio
async def test_smart_rename_calls_preflight_before_rename() -> None:
    """Ensure smart_rename runs prepare_rename preflight then delegates to rope."""
    pyright = AsyncMock()
    rope = AsyncMock()

    pyright.prepare_rename.return_value = object()  # non-None = valid rename target
    rope.rename.return_value = RefactorResult(
        edits=[_edit("/repo/a.py")],
        files_affected=["/repo/a.py"],
        description="rename",
        applied=False,
    )

    result = await composite.smart_rename(pyright, rope, "/repo/a.py", 1, 2, "new_name", apply=False)

    assert result.applied is False
    pyright.prepare_rename.assert_awaited_once_with("/repo/a.py", 1, 2)
    rope.rename.assert_awaited_once_with("/repo/a.py", 1, 2, "new_name", False)


@pytest.mark.asyncio
async def test_smart_rename_apply_refreshes_diagnostics() -> None:
    """Ensure apply mode notifies changed files and includes diagnostics."""
    pyright = AsyncMock()
    rope = AsyncMock()

    pyright.prepare_rename.return_value = object()  # non-None = valid rename target
    rope.rename.return_value = RefactorResult(
        edits=[_edit("/repo/a.py"), _edit("/repo/b.py")],
        files_affected=["/repo/a.py", "/repo/b.py"],
        description="rename",
        applied=True,
    )
    pyright.get_diagnostics.side_effect = [[_diag("/repo/a.py", 1)], [_diag("/repo/b.py", 2)]]

    result = await composite.smart_rename(pyright, rope, "/repo/a.py", 1, 2, "new_name", apply=True)

    assert result.diagnostics_after is not None
    assert len(result.diagnostics_after) == 2
    pyright.notify_file_changed.assert_any_await("/repo/a.py")
    pyright.notify_file_changed.assert_any_await("/repo/b.py")


@pytest.mark.asyncio
async def test_diff_preview_builds_unified_diff(tmp_path: Path) -> None:
    """Ensure diff preview returns a unified diff per affected file."""
    target = tmp_path / "sample.py"
    target.write_text("x = 1\n", encoding="utf-8")

    result = await composite.diff_preview([
        TextEdit(
            file_path=str(target),
            range=Range(start=Position(line=0, character=4), end=Position(line=0, character=5)),
            new_text="2",
        )
    ])

    assert len(result) == 1
    assert "-x = 1" in result[0].unified_diff
    assert "+x = 2" in result[0].unified_diff
