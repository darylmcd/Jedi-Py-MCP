"""Unit tests for navigation tool behavior and backend fallback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import CallHierarchyItem, Location, Position, Range, SymbolOutlineItem
from python_refactor_mcp.tools import navigation


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


def _location(path: str, line: int, character: int) -> Location:
    return Location(
        file_path=path,
        range=Range(
            start=Position(line=line, character=character),
            end=Position(line=line, character=character + 1),
        ),
    )


@pytest.mark.asyncio
async def test_call_hierarchy_collects_depth_for_both_directions() -> None:
    """Ensure traversal honors depth and both directions."""
    pyright = AsyncMock()

    root = _item("root", "/repo/a.py", 1)
    caller = _item("caller", "/repo/b.py", 2)
    grand_caller = _item("grand", "/repo/c.py", 3)
    callee = _item("callee", "/repo/d.py", 4)

    pyright.prepare_call_hierarchy.return_value = [root]

    async def _incoming(item: CallHierarchyItem) -> list[CallHierarchyItem]:
        if item.name == "root":
            return [caller]
        if item.name == "caller":
            return [grand_caller]
        return []

    async def _outgoing(item: CallHierarchyItem) -> list[CallHierarchyItem]:
        if item.name == "root":
            return [callee]
        return []

    pyright.get_incoming_calls.side_effect = _incoming
    pyright.get_outgoing_calls.side_effect = _outgoing

    result = await navigation.call_hierarchy(pyright, "/repo/a.py", 1, 0, direction="both", depth=2)

    assert [item.name for item in result.callers] == ["caller", "grand"]
    assert [item.name for item in result.callees] == ["callee"]


@pytest.mark.asyncio
async def test_call_hierarchy_validates_direction_and_depth() -> None:
    """Ensure direction and depth validation errors are raised."""
    pyright = AsyncMock()

    with pytest.raises(ValueError, match="Invalid direction"):
        await navigation.call_hierarchy(pyright, "/repo/a.py", 0, 0, direction="sideways", depth=1)

    with pytest.raises(ValueError, match="depth"):
        await navigation.call_hierarchy(pyright, "/repo/a.py", 0, 0, direction="both", depth=0)


@pytest.mark.asyncio
async def test_goto_definition_falls_back_to_jedi() -> None:
    """Ensure Jedi is queried when Pyright returns no definitions."""
    pyright = AsyncMock()
    jedi = AsyncMock()

    pyright.get_definition.return_value = []
    jedi.goto_definition.return_value = [_location("/repo/a.py", 5, 2)]

    result = await navigation.goto_definition(pyright, jedi, "/repo/a.py", 5, 2)

    assert len(result) == 1
    assert result[0].file_path == "/repo/a.py"
    jedi.goto_definition.assert_awaited_once()


def _config(tmp_path: Path) -> ServerConfig:
    return ServerConfig(
        workspace_root=tmp_path,
        python_executable=tmp_path / ".venv" / "Scripts" / "python.exe",
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )


@pytest.mark.asyncio
async def test_get_symbol_outline_collects_workspace_items(tmp_path: Path) -> None:
    """Ensure outline collection walks the workspace and returns sorted items."""
    first = tmp_path / "a.py"
    second = tmp_path / "nested" / "b.py"
    second.parent.mkdir(parents=True, exist_ok=True)
    first.write_text("def a():\n    pass\n", encoding="utf-8")
    second.write_text("def b():\n    pass\n", encoding="utf-8")

    pyright = AsyncMock()
    first_item = SymbolOutlineItem(
        name="a",
        kind="function",
        file_path=str(first),
        range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
        selection_range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
    )
    second_item = SymbolOutlineItem(
        name="b",
        kind="function",
        file_path=str(second),
        range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
        selection_range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
    )
    pyright.get_document_symbols.side_effect = [[first_item], [second_item]]

    result = await navigation.get_symbol_outline(pyright, _config(tmp_path))

    assert [item.name for item in result] == ["a", "b"]


@pytest.mark.asyncio
async def test_find_implementations_deduplicates_results() -> None:
    """Ensure implementation results are de-duplicated and sorted."""
    pyright = AsyncMock()
    shared = _location("/repo/a.py", 1, 2)
    pyright.get_implementation.return_value = [shared, shared, _location("/repo/b.py", 0, 0)]

    result = await navigation.find_implementations(pyright, "/repo/a.py", 1, 2)

    assert [item.file_path for item in result] == ["/repo/a.py", "/repo/b.py"]
