"""Unit tests for search tool orchestration and fallbacks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.models import Diagnostic, ImportSuggestion, Location, Position, Range, SymbolInfo
from python_refactor_mcp.tools import search
from tests.helpers import make_config as _config


def _location(path: Path, line: int, character: int) -> Location:
    return Location(
        file_path=str(path.resolve()),
        range=Range(
            start=Position(line=line, character=character),
            end=Position(line=line, character=character + 1),
        ),
    )


@pytest.mark.asyncio
async def test_find_constructors_filters_for_call_sites(tmp_path: Path) -> None:
    """Ensure constructor search returns only real call sites for class usage."""
    source = tmp_path / "sample.py"
    source.write_text(
        "class Widget:\n"
        "    pass\n\n"
        "x = Widget(1, size=2)\n"
        "class Sub(Widget):\n"
        "    pass\n",
        encoding="utf-8",
    )

    pyright = AsyncMock()
    pyright.get_references.return_value = [
        _location(source, 0, 6),
        _location(source, 3, 4),
    ]

    results = await search.find_constructors(pyright, _config(tmp_path), "Widget", str(source))

    assert len(results) == 1
    assert results[0].class_name == "Widget"
    assert results[0].arguments == ["1", "size=2"]


@pytest.mark.asyncio
async def test_structural_search_returns_matches(tmp_path: Path) -> None:
    """Ensure structural search returns matched snippets and ranges."""
    source = tmp_path / "sample.py"
    source.write_text(
        "def f():\n"
        "    print('a')\n"
        "    print('b')\n",
        encoding="utf-8",
    )

    results, files_scanned, scan_failures = await search.structural_search(
        _config(tmp_path),
        "m.Call(func=m.Name('print'))",
        str(source),
    )

    assert len(results) == 2
    assert all("print" in item.matched_text for item in results)
    assert files_scanned == 1
    assert scan_failures == []


@pytest.mark.asyncio
async def test_structural_search_reports_parse_failures(tmp_path: Path) -> None:
    """Invalid files are visible to callers instead of disappearing from results."""
    (tmp_path / "valid.py").write_text("print('ok')\n", encoding="utf-8")
    invalid = tmp_path / "invalid.py"
    invalid.write_text("def broken(:\n", encoding="utf-8")

    results, files_scanned, scan_failures = await search.structural_search(
        _config(tmp_path), "m.Call(func=m.Name('print'))"
    )

    assert len(results) == 1
    assert files_scanned == 1
    assert len(scan_failures) == 1
    assert scan_failures[0].file_path == str(invalid.resolve())
    assert scan_failures[0].phase == "read_or_parse"


@pytest.mark.asyncio
async def test_dead_code_detection_marks_unreferenced_symbols(tmp_path: Path) -> None:
    """Ensure dead code detection flags symbols with zero references."""
    source = tmp_path / "sample.py"
    source.write_text(
        "def dead_func():\n"
        "    return 1\n\n"
        "class DeadClass:\n"
        "    pass\n",
        encoding="utf-8",
    )

    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []
    pyright.get_references.return_value = []

    result = await search.dead_code_detection(pyright, _config(tmp_path), str(source))

    names = {item.name for item in result.items}
    assert "dead_func" in names
    assert "DeadClass" in names


@pytest.mark.asyncio
async def test_dead_code_detection_reports_diagnostic_failures(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text("# no symbols\n", encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_diagnostics.side_effect = RuntimeError("backend unavailable")

    result = await search.dead_code_detection(pyright, _config(tmp_path), str(source))

    assert len(result.scan_failures) == 1
    assert result.scan_failures[0].file_path == str(source.resolve())
    assert result.scan_failures[0].error_type == "RuntimeError"


@pytest.mark.asyncio
async def test_suggest_imports_uses_jedi_fallback(tmp_path: Path) -> None:
    """Ensure suggest_imports falls back to Jedi when Pyright code actions are empty."""
    source = tmp_path / "sample.py"
    source.write_text("value = OrderedDict()\n", encoding="utf-8")

    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = [
        Diagnostic(
            file_path=str(source.resolve()),
            range=Range(
                start=Position(line=0, character=8),
                end=Position(line=0, character=19),
            ),
            severity="error",
            message="\"OrderedDict\" is not defined",
            code="reportUndefinedVariable",
        )
    ]
    pyright.get_code_actions.return_value = []

    jedi = AsyncMock()
    jedi.search_names.return_value = [
        ImportSuggestion(
            symbol="OrderedDict",
            module="collections",
            import_statement="from collections import OrderedDict",
        )
    ]

    suggestions = await search.suggest_imports(pyright, jedi, "OrderedDict", str(source))

    assert len(suggestions) == 1
    assert suggestions[0].module == "collections"


@pytest.mark.asyncio
async def test_search_symbols_merges_pyright_and_jedi_results() -> None:
    """Ensure symbol search merges and de-duplicates results across backends."""
    pyright = AsyncMock()
    jedi = AsyncMock()
    shared = SymbolInfo(
        name="Widget",
        kind="class",
        file_path="/repo/a.py",
        range=Range(start=Position(line=0, character=0), end=Position(line=0, character=6)),
        container=None,
    )
    pyright.workspace_symbol.return_value = [shared]
    jedi.search_symbols.return_value = [shared, SymbolInfo(
        name="WidgetFactory",
        kind="function",
        file_path="/repo/b.py",
        range=Range(start=Position(line=3, character=0), end=Position(line=3, character=13)),
        container=None,
    )]

    result = await search.search_symbols(pyright, jedi, "Widget")

    assert [item.name for item in result.items] == ["Widget", "WidgetFactory"]
    assert result.total_count == 2
    assert result.backend_failures == []

    limited = await search.search_symbols(pyright, jedi, "Widget", limit=1)
    assert [item.name for item in limited.items] == ["Widget"]
    assert limited.total_count == 2
    assert limited.truncated is True


# ── PR 3-B: Invalid-input / failure-path unit tests ──


@pytest.mark.asyncio
async def test_search_symbols_both_fail_reports_backend_failures() -> None:
    """When both backends raise, preserve stable failure provenance."""
    pyright = AsyncMock()
    jedi = AsyncMock()
    pyright.workspace_symbol.side_effect = RuntimeError("pyright crashed")
    jedi.search_symbols.side_effect = RuntimeError("jedi crashed")

    result = await search.search_symbols(pyright, jedi, "Widget")

    assert result.items == []
    assert [(failure.backend, failure.operation, failure.error_type) for failure in result.backend_failures] == [
        ("pyright", "workspace_symbol", "RuntimeError"),
        ("jedi", "search_symbols", "RuntimeError"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["dead_code_detection", "unused_symbol_sweep"])
async def test_symbol_scans_report_parse_failures(tool_name: str, tmp_path: Path) -> None:
    """A malformed file is a visible partial scan, not an empty success."""
    invalid = tmp_path / "invalid.py"
    invalid.write_text("def broken(:\n", encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await getattr(search, tool_name)(pyright, _config(tmp_path), str(invalid))

    assert result.items == []
    assert len(result.scan_failures) == 1
    assert result.scan_failures[0].file_path == str(invalid.resolve())
    assert result.scan_failures[0].phase == "symbol_scan"
    assert result.scan_failures[0].error_type == "SyntaxError"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["dead_code_detection", "unused_symbol_sweep"])
async def test_symbol_scans_report_missing_files(tool_name: str, tmp_path: Path) -> None:
    """An explicitly requested missing file remains visible in scan metadata."""
    missing = tmp_path / "missing.py"
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await getattr(search, tool_name)(pyright, _config(tmp_path), str(missing))

    assert result.items == []
    assert len(result.scan_failures) == 1
    assert result.scan_failures[0].file_path == str(missing.resolve())
    assert result.scan_failures[0].phase == "symbol_scan"
    assert result.scan_failures[0].error_type == "FileNotFoundError"


@pytest.mark.asyncio
async def test_unused_symbol_sweep_flags_unreferenced_exports(tmp_path: Path) -> None:
    """Public exports with no cross-file references are flagged."""
    source = tmp_path / "api.py"
    source.write_text(
        "def public_unused():\n    return 1\n\nclass PublicWidget:\n    pass\n",
        encoding="utf-8",
    )

    pyright = AsyncMock()
    pyright.get_references.return_value = []

    result = await search.unused_symbol_sweep(pyright, _config(tmp_path), str(source))

    names = {item.name for item in result.items}
    assert "public_unused" in names
    assert "PublicWidget" in names


@pytest.mark.asyncio
async def test_unused_symbol_sweep_reports_reference_failures(tmp_path: Path) -> None:
    source = tmp_path / "api.py"
    source.write_text("def public_name():\n    return 1\n", encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_references.side_effect = RuntimeError("backend unavailable")

    result = await search.unused_symbol_sweep(pyright, _config(tmp_path), str(source))

    assert len(result.scan_failures) == 1
    assert result.scan_failures[0].subject == "public_name"


@pytest.mark.asyncio
async def test_unused_symbol_sweep_ignores_cross_file_referenced_exports(tmp_path: Path) -> None:
    """A symbol referenced from another file is not flagged."""
    source = tmp_path / "api.py"
    source.write_text("def used():\n    return 1\n", encoding="utf-8")
    other = tmp_path / "caller.py"

    pyright = AsyncMock()
    pyright.get_references.return_value = [_location(other, 0, 0)]

    result = await search.unused_symbol_sweep(pyright, _config(tmp_path), str(source))

    assert result.items == []


@pytest.mark.asyncio
async def test_unused_symbol_sweep_skips_externally_registered_symbols(tmp_path: Path) -> None:
    """Symbols decorated by an external registrar (mcp/tool) are skipped."""
    source = tmp_path / "api.py"
    source.write_text(
        "import mcp\n\n@mcp.tool\ndef registered():\n    return 1\n\ndef plain_unused():\n    return 2\n",
        encoding="utf-8",
    )

    pyright = AsyncMock()
    pyright.get_references.return_value = []

    result = await search.unused_symbol_sweep(pyright, _config(tmp_path), str(source))

    names = {item.name for item in result.items}
    assert "registered" not in names
    assert "plain_unused" in names


@pytest.mark.asyncio
async def test_unused_symbol_sweep_respects_dunder_all(tmp_path: Path) -> None:
    """Only __all__-listed names are in scope when the module defines __all__."""
    source = tmp_path / "api.py"
    source.write_text(
        '__all__ = ["exported"]\n\ndef exported():\n    return 1\n\ndef not_exported():\n    return 2\n',
        encoding="utf-8",
    )

    pyright = AsyncMock()
    pyright.get_references.return_value = []

    result = await search.unused_symbol_sweep(pyright, _config(tmp_path), str(source))

    names = {item.name for item in result.items}
    assert names == {"exported"}
