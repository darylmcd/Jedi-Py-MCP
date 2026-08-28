"""Unit tests for the test_impact_select analysis tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.models import CallHierarchyItem, Position, Range, SymbolAnchor
from python_refactor_mcp.tools import analysis


def _item(name: str, path: str, line: int) -> CallHierarchyItem:
    return CallHierarchyItem(
        name=name,
        kind="function",
        file_path=path,
        range=Range(
            start=Position(line=line, character=0),
            end=Position(line=line, character=1),
        ),
    )


@pytest.mark.asyncio
async def test_test_impact_select_returns_test_node_ids() -> None:
    """Test-file callers become pytest node IDs; the symbol name is the root."""
    root = _item("target", "/repo/mod.py", 1)
    test_caller = _item("test_target", "/repo/tests/test_mod.py", 5)
    prod_caller = _item("other", "/repo/mod2.py", 9)

    pyright = AsyncMock()
    pyright.prepare_call_hierarchy.return_value = [root]

    async def _incoming(item: CallHierarchyItem) -> list[CallHierarchyItem]:
        if item.name == "target":
            return [test_caller, prod_caller]
        return []

    pyright.get_incoming_calls.side_effect = _incoming

    result = await analysis.test_impact_select(
        pyright, [SymbolAnchor(file_path="/repo/mod.py", line=1, character=0)]
    )

    assert len(result.entries) == 1
    entry = result.entries[0]
    assert entry.symbol == "target"
    assert entry.pytest_node_ids == ["/repo/tests/test_mod.py::test_target"]
    assert entry.affected_test_files == ["/repo/tests/test_mod.py"]
    assert result.total_affected_tests == 1


@pytest.mark.asyncio
async def test_test_impact_select_excludes_non_test_callers() -> None:
    """Callers outside test files are dropped from the result."""
    root = _item("target", "/repo/mod.py", 1)
    prod_caller = _item("other", "/repo/mod2.py", 9)

    pyright = AsyncMock()
    pyright.prepare_call_hierarchy.return_value = [root]

    async def _incoming(item: CallHierarchyItem) -> list[CallHierarchyItem]:
        if item.name == "target":
            return [prod_caller]
        return []

    pyright.get_incoming_calls.side_effect = _incoming

    result = await analysis.test_impact_select(
        pyright, [SymbolAnchor(file_path="/repo/mod.py", line=1, character=0)]
    )

    assert result.entries[0].pytest_node_ids == []
    assert result.entries[0].affected_test_files == []
    assert result.total_affected_tests == 0


@pytest.mark.asyncio
async def test_test_impact_select_handles_no_callers() -> None:
    """A symbol with no callers yields a valid empty entry, not an error."""
    root = _item("target", "/repo/mod.py", 1)

    pyright = AsyncMock()
    pyright.prepare_call_hierarchy.return_value = [root]
    pyright.get_incoming_calls.return_value = []

    result = await analysis.test_impact_select(
        pyright, [SymbolAnchor(file_path="/repo/mod.py", line=1, character=0)]
    )

    assert result.entries[0].symbol == "target"
    assert result.entries[0].pytest_node_ids == []
    assert result.total_affected_tests == 0
    assert result.truncated is False
