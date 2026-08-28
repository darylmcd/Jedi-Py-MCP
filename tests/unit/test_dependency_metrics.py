"""Tests for dependency-graph scan diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest

from python_refactor_mcp.tools import metrics
from tests.helpers import make_config


@pytest.mark.asyncio
async def test_module_dependencies_reports_parse_failures(tmp_path: Path) -> None:
    valid = tmp_path / "valid.py"
    valid.write_text("import os\n", encoding="utf-8")
    invalid = tmp_path / "invalid.py"
    invalid.write_text("def broken(:\n", encoding="utf-8")

    result = await metrics.get_module_dependencies(
        make_config(tmp_path), file_paths=[str(valid), str(invalid)]
    )

    assert len(result.scan_failures) == 1
    assert result.scan_failures[0].file_path == str(invalid.resolve())
    assert result.scan_failures[0].error_type == "SyntaxError"
