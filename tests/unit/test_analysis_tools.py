"""Unit tests for analysis tool orchestration and fallback behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.models import Diagnostic, Location, Position, Range, TypeInfo
from python_refactor_mcp.tools import analysis


def _location(path: str, line: int, character: int) -> Location:
    return Location(
        file_path=path,
        range=Range(
            start=Position(line=line, character=character),
            end=Position(line=line, character=character + 1),
        ),
    )


@pytest.mark.asyncio
async def test_find_references_falls_back_to_jedi_when_pyright_is_empty() -> None:
    """Ensure Jedi fallback runs when Pyright returns no references."""
    pyright = AsyncMock()
    jedi = AsyncMock()
    pyright.get_references.return_value = []
    jedi.get_references.return_value = [_location("/repo/a.py", 2, 1)]

    result = await analysis.find_references(pyright, jedi, "/repo/a.py", 2, 1)

    assert result.source == "jedi"
    assert result.total_count == 1
    pyright.get_references.assert_awaited_once()
    jedi.get_references.assert_awaited_once()


@pytest.mark.asyncio
async def test_find_references_merges_and_deduplicates_results() -> None:
    """Ensure merged reference results are de-duplicated and sorted."""
    pyright = AsyncMock()
    jedi = AsyncMock()

    shared = _location("/repo/a.py", 1, 2)
    pyright.get_references.return_value = [shared]
    jedi.get_references.return_value = [shared, _location("/repo/b.py", 3, 4)]

    result = await analysis.find_references(pyright, jedi, "/repo/a.py", 1, 2)

    assert result.source == "combined"
    assert result.total_count == 2
    assert [item.file_path for item in result.references] == ["/repo/a.py", "/repo/b.py"]


@pytest.mark.asyncio
async def test_get_type_info_uses_jedi_when_pyright_is_unknown() -> None:
    """Ensure unknown Pyright hover falls back to Jedi inference."""
    pyright = AsyncMock()
    jedi = AsyncMock()

    pyright.get_hover.return_value = TypeInfo(
        expression="/repo/a.py:0:0",
        type_string="Unknown",
        documentation=None,
        source="pyright",
    )
    inferred = TypeInfo(
        expression="/repo/a.py:0:0",
        type_string="module.symbol.Type",
        documentation="doc",
        source="jedi",
    )
    jedi.infer_type.return_value = inferred

    result = await analysis.get_type_info(pyright, jedi, "/repo/a.py", 0, 0)

    assert result is inferred
    jedi.infer_type.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_diagnostics_filters_and_sorts() -> None:
    """Ensure diagnostics filtering is case-insensitive and output is sorted."""
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = [
        Diagnostic(
            file_path="/repo/b.py",
            range=Range(start=Position(line=9, character=0), end=Position(line=9, character=1)),
            severity="warning",
            message="warn",
            code=None,
        ),
        Diagnostic(
            file_path="/repo/a.py",
            range=Range(start=Position(line=1, character=1), end=Position(line=1, character=3)),
            severity="warning",
            message="warn2",
            code=None,
        ),
        Diagnostic(
            file_path="/repo/a.py",
            range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
            severity="error",
            message="err",
            code=None,
        ),
    ]

    filtered = await analysis.get_diagnostics(pyright, severity_filter="WARNING")

    assert [(item.file_path, item.range.start.line) for item in filtered] == [
        ("/repo/a.py", 1),
        ("/repo/b.py", 9),
    ]


@pytest.mark.asyncio
async def test_get_diagnostics_rejects_invalid_severity() -> None:
    """Ensure invalid severity values fail fast with a clear error."""
    pyright = AsyncMock()

    with pytest.raises(ValueError, match="Invalid severity_filter"):
        await analysis.get_diagnostics(pyright, severity_filter="critical")
