"""Regression tests for partial-capable metrics and scanner results."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.errors import ToolInputError
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


def _layered_package(root: Path) -> Path:
    """Create ``pkg`` with a ``backends`` layer importing the higher ``tools`` layer."""
    pkg = root / "pkg"
    (pkg / "tools").mkdir(parents=True)
    (pkg / "backends").mkdir()
    for init in (pkg / "__init__.py", pkg / "tools" / "__init__.py", pkg / "backends" / "__init__.py"):
        init.write_text("", encoding="utf-8")
    (pkg / "tools" / "api.py").write_text("VALUE = 1\n", encoding="utf-8")
    (pkg / "backends" / "store.py").write_text(
        "import os, pkg.tools.api\nfrom ..tools import api\nfrom . import sibling\n",
        encoding="utf-8",
    )
    (pkg / "backends" / "sibling.py").write_text("", encoding="utf-8")
    return pkg


def _violation_keys(result: object) -> list[tuple[str, str, int, int, int]]:
    return sorted(
        (Path(v.source_module).name, v.target_module, v.source_layer, v.target_layer, v.import_line)
        for v in result.items  # type: ignore[attr-defined]
    )


@pytest.mark.asyncio
async def test_layer_dotted_patterns_match_component_patterns(tmp_path: Path) -> None:
    _layered_package(tmp_path)
    config = make_config(tmp_path)

    dotted = await metrics.check_layer_violations(config, [["pkg.tools"], ["pkg.backends"]])
    component = await metrics.check_layer_violations(config, [["tools"], ["backends"]])

    expected = [
        ("store.py", "pkg.tools", 1, 0, 1),
        ("store.py", "pkg.tools.api", 1, 0, 0),
    ]
    assert _violation_keys(dotted) == expected
    assert _violation_keys(component) == expected
    assert dotted.unmatched_layer_patterns == []
    assert component.unmatched_layer_patterns == []


@pytest.mark.asyncio
async def test_layer_dotted_patterns_honour_src_layout(tmp_path: Path) -> None:
    _layered_package(tmp_path / "src")

    result = await metrics.check_layer_violations(
        make_config(tmp_path), [["pkg.tools"], ["pkg.backends"]]
    )

    assert _violation_keys(result) == [
        ("store.py", "pkg.tools", 1, 0, 1),
        ("store.py", "pkg.tools.api", 1, 0, 0),
    ]


@pytest.mark.asyncio
async def test_layer_import_checks_every_alias(tmp_path: Path) -> None:
    _layered_package(tmp_path)
    store = tmp_path / "pkg" / "backends" / "store.py"
    store.write_text("import pkg.tools.api, os\n", encoding="utf-8")

    result = await metrics.check_layer_violations(
        make_config(tmp_path), [["tools"], ["backends"]], [str(store)]
    )

    assert _violation_keys(result) == [("store.py", "pkg.tools.api", 1, 0, 0)]


@pytest.mark.asyncio
async def test_layer_reports_patterns_matching_no_scanned_module(tmp_path: Path) -> None:
    _layered_package(tmp_path)

    result = await metrics.check_layer_violations(
        make_config(tmp_path), [["pkg.tools", "pkg.web"], ["pkg.backends"], ["domain"]]
    )

    assert result.unmatched_layer_patterns == ["pkg.web", "domain"]


@pytest.mark.asyncio
async def test_code_metrics_ranks_by_cyclomatic_and_caps_after_aggregates(tmp_path: Path) -> None:
    module = tmp_path / "ranked.py"
    module.write_text(
        "def flat():\n"
        "    return 1\n"
        "\n"
        "def branchy(a, b):\n"
        "    if a:\n"
        "        return 1\n"
        "    if b:\n"
        "        return 2\n"
        "    return 3\n"
        "\n"
        "def one_branch(a):\n"
        "    if a:\n"
        "        return 1\n"
        "    return 2\n",
        encoding="utf-8",
    )

    full = await metrics.code_metrics(str(module))
    capped = await metrics.code_metrics(str(module), limit=2)

    assert [f.name for f in full.functions] == ["branchy", "one_branch", "flat"]
    assert full.truncated is False
    assert [f.name for f in capped.functions] == ["branchy", "one_branch"]
    assert capped.truncated is True
    assert capped.total_functions == 3
    assert capped.max_cyclomatic == 3
    assert capped.avg_cyclomatic == full.avg_cyclomatic == 2.0


@pytest.mark.asyncio
async def test_module_dependencies_cap_edges_but_keep_full_graph(tmp_path: Path) -> None:
    _layered_package(tmp_path)
    config = make_config(tmp_path)

    full = await metrics.get_module_dependencies(config)
    capped = await metrics.get_module_dependencies(config, limit=1)

    assert full.total_dependencies == len(full.dependencies) > 1
    assert full.truncated is False
    assert capped.dependencies == full.dependencies[:1]
    assert capped.total_dependencies == full.total_dependencies
    assert capped.truncated is True
    assert capped.modules == full.modules
    assert capped.circular_dependencies == full.circular_dependencies


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1])
async def test_metrics_limits_reject_non_positive_values(tmp_path: Path, limit: int) -> None:
    module = tmp_path / "m.py"
    module.write_text("def f():\n    return 1\n", encoding="utf-8")

    with pytest.raises(ToolInputError, match="limit"):
        await metrics.code_metrics(str(module), limit=limit)
    with pytest.raises(ToolInputError, match="limit"):
        await metrics.get_module_dependencies(make_config(tmp_path), limit=limit)
