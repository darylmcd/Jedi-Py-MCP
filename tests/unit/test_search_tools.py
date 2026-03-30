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

    results, files_scanned = await search.structural_search(
        _config(tmp_path),
        "m.Call(func=m.Name('print'))",
        str(source),
    )

    assert len(results) == 2
    assert all("print" in item.matched_text for item in results)
    assert files_scanned == 1


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

    results = await search.search_symbols(pyright, jedi, "Widget")

    assert [item.name for item in results] == ["Widget", "WidgetFactory"]
