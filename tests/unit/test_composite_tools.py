"""Unit tests for composite tool orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from python_refactor_mcp.models import Position, Range, TextEdit
from python_refactor_mcp.tools import composite


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
