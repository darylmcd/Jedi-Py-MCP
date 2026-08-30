"""Regression tests for partial-capable metrics and scanner results."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.models import Diagnostic, Position, Range
from python_refactor_mcp.tools import metrics
from python_refactor_mcp.tools.metrics.security import security_scan
from python_refactor_mcp.tools.metrics.test_map import get_test_coverage_map
from tests.helpers import make_config


def _invalid_module(tmp_path: Path) -> Path:
    path = tmp_path / "invalid.py"
    path.write_text("def broken(:\n", encoding="utf-8")
    return path


def _assert_parse_failure(result: object, invalid: Path) -> None:
    failures = result.scan_failures  # type: ignore[attr-defined]
    assert result.files_scanned == 0  # type: ignore[attr-defined]
    assert len(failures) == 1
    assert failures[0].file_path == str(invalid.resolve())
    assert failures[0].phase == "read_or_parse"
    assert failures[0].error_type == "SyntaxError"


@pytest.mark.asyncio
async def test_security_scan_reports_unparseable_file(tmp_path: Path) -> None:
    invalid = _invalid_module(tmp_path)

    result = await security_scan(file_path=str(invalid))

    assert result.findings == []
    _assert_parse_failure(result, invalid)


@pytest.mark.asyncio
async def test_code_metrics_reports_unparseable_file(tmp_path: Path) -> None:
    invalid = _invalid_module(tmp_path)

    result = await metrics.code_metrics(str(invalid))

    assert result.functions == []
    _assert_parse_failure(result, invalid)


@pytest.mark.asyncio
async def test_type_coverage_reports_unparseable_file(tmp_path: Path) -> None:
    invalid = _invalid_module(tmp_path)

    result = await metrics.get_type_coverage(str(invalid))

    assert result.total_functions == 0
    _assert_parse_failure(result, invalid)


@pytest.mark.asyncio
async def test_duplicate_scan_reports_unparseable_file(tmp_path: Path) -> None:
    invalid = _invalid_module(tmp_path)

    result = await metrics.find_duplicated_code(str(invalid))

    assert result.items == []
    _assert_parse_failure(result, invalid)


@pytest.mark.asyncio
async def test_layer_scan_reports_unparseable_file(tmp_path: Path) -> None:
    invalid = _invalid_module(tmp_path)

    result = await metrics.check_layer_violations(
        make_config(tmp_path), [["presentation"], ["domain"]], [str(invalid)]
    )

    assert result.items == []
    _assert_parse_failure(result, invalid)


@pytest.mark.asyncio
async def test_coupling_metrics_preserve_dependency_scan_failures(tmp_path: Path) -> None:
    invalid = _invalid_module(tmp_path)

    result = await metrics.get_coupling_metrics(make_config(tmp_path), file_paths=[str(invalid)])

    assert result.items == []
    _assert_parse_failure(result, invalid)


@pytest.mark.asyncio
async def test_test_coverage_map_reports_unparseable_file(tmp_path: Path) -> None:
    invalid = _invalid_module(tmp_path)

    result = await get_test_coverage_map(AsyncMock(), file_path=str(invalid))

    assert result.entries == []
    _assert_parse_failure(result, invalid)


@pytest.mark.asyncio
async def test_test_coverage_map_reports_reference_failure_without_false_uncovered_entry(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    source.write_text("def public_api():\n    return 1\n", encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_references.side_effect = RuntimeError("sensitive backend detail")

    result = await get_test_coverage_map(pyright, file_path=str(source))

    assert result.entries == []
    assert result.files_scanned == 1
    assert len(result.scan_failures) == 1
    assert result.scan_failures[0].phase == "references"
    assert result.scan_failures[0].error_type == "RuntimeError"
    assert "sensitive" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_unused_imports_use_per_file_fallback_and_report_parse_failures(tmp_path: Path) -> None:
    first = tmp_path / "first.py"
    first.write_text("import os\nimport xml.etree\n", encoding="utf-8")
    second = tmp_path / "second.py"
    second.write_text("import sys\n", encoding="utf-8")
    invalid = _invalid_module(tmp_path)
    pyright = AsyncMock()
    pyright.get_diagnostics.side_effect = [
        [
            Diagnostic(
                file_path=str(first.resolve()),
                range=Range(
                    start=Position(line=0, character=7),
                    end=Position(line=0, character=9),
                ),
                severity="warning",
                message='"os" is not accessed',
                code="reportUnusedImport",
            )
        ],
        [],
    ]

    result = await metrics.find_unused_imports(
        pyright,
        str(first),
        [str(first), str(second), str(invalid)],
    )

    assert {item.name for item in result.items} == {"os", "xml", "sys"}
    assert result.files_scanned == 2
    assert len(result.scan_failures) == 1
    assert result.scan_failures[0].file_path == str(invalid.resolve())
    assert result.scan_failures[0].error_type == "SyntaxError"
