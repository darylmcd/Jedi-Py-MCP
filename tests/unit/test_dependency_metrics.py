"""Tests for dependency-graph scan diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest

from python_refactor_mcp.tools import metrics
from tests.helpers import make_config


def _write_module(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


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


@pytest.mark.asyncio
async def test_module_dependencies_reports_shared_node_cycle_as_one_component(tmp_path: Path) -> None:
    first = _write_module(tmp_path / "first.py", "import second\n")
    second = _write_module(tmp_path / "second.py", "import first\nimport third\n")
    third = _write_module(tmp_path / "third.py", "import second\n")

    result = await metrics.get_module_dependencies(make_config(tmp_path))

    expected_component = sorted(str(path.resolve()) for path in (first, second, third))
    assert result.circular_dependencies == [expected_component]


@pytest.mark.asyncio
async def test_module_dependencies_resolves_relative_src_package_cycle_with_edge_evidence(tmp_path: Path) -> None:
    package = tmp_path / "src" / "example"
    _write_module(package / "__init__.py", "")
    first = _write_module(package / "first.py", "from . import second\n")
    second = _write_module(package / "second.py", "from .nested import third\n")
    _write_module(package / "nested" / "__init__.py", "")
    third = _write_module(package / "nested" / "third.py", "from .. import first\n")

    result = await metrics.get_module_dependencies(make_config(tmp_path))

    expected_component = sorted(str(path.resolve()) for path in (first, second, third))
    assert result.circular_dependencies == [expected_component]
    internal_edges = {
        (dependency.source, dependency.target): (dependency.import_name, dependency.line)
        for dependency in result.dependencies
        if dependency.target in expected_component
    }
    assert internal_edges == {
        (str(first.resolve()), str(second.resolve())): (".second", 0),
        (str(second.resolve()), str(third.resolve())): (".nested.third", 0),
        (str(third.resolve()), str(first.resolve())): ("..first", 0),
    }


@pytest.mark.asyncio
async def test_module_dependencies_excludes_virtual_environment_sources(tmp_path: Path) -> None:
    project_module = _write_module(tmp_path / "project.py", "import os\n")
    _write_module(tmp_path / ".venv" / "library.py", "import project\n")

    result = await metrics.get_module_dependencies(make_config(tmp_path))

    assert result.modules == [str(project_module.resolve())]


@pytest.mark.asyncio
async def test_module_dependencies_does_not_resolve_relative_import_beyond_top_package(tmp_path: Path) -> None:
    source = _write_module(tmp_path / "source.py", "from . import target\n")
    target = _write_module(tmp_path / "target.py", "import source\n")

    result = await metrics.get_module_dependencies(make_config(tmp_path))

    source_dependency = next(
        dependency for dependency in result.dependencies if dependency.source == str(source.resolve())
    )
    assert source_dependency.import_name == ".target"
    assert source_dependency.target == ".target"
    assert source_dependency.target != str(target.resolve())
    assert result.circular_dependencies == []


@pytest.mark.asyncio
async def test_module_dependencies_resolves_relative_import_from_sources_own_root(tmp_path: Path) -> None:
    root_package = tmp_path / "package"
    source = _write_module(root_package / "source.py", "from . import target\n")
    expected_target = _write_module(root_package / "target.py", "")
    _write_module(tmp_path / "src" / "package" / "target.py", "")

    result = await metrics.get_module_dependencies(make_config(tmp_path), file_path=str(source))

    assert result.dependencies[0].target == str(expected_target.resolve())
