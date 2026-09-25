"""Unit tests for navigation tool behavior and backend fallback."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.errors import LspFeatureUnsupportedError, ToolInputError
from python_refactor_mcp.models import (
    CallHierarchyItem,
    FoldingRange,
    Position,
    Range,
    SelectionRangeResult,
    SymbolOutlineItem,
    SymbolOutlineResult,
    TypeHierarchyItem,
)
from python_refactor_mcp.tools import navigation
from python_refactor_mcp.tools.navigation.outline import _apply_node_budget
from tests.helpers import make_config as _config
from tests.helpers import make_location as _location


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

    with pytest.raises(ToolInputError, match="^direction is invalid"):
        await navigation.call_hierarchy(pyright, "/repo/a.py", 0, 0, direction="sideways", depth=1)

    with pytest.raises(ToolInputError, match="^depth"):
        await navigation.call_hierarchy(pyright, "/repo/a.py", 0, 0, direction="both", depth=0)

    with pytest.raises(ToolInputError, match="^direction is invalid"):
        await navigation.type_hierarchy(pyright, "/repo/a.py", 0, 0, direction="sideways", depth=1)

    pyright.prepare_call_hierarchy.assert_not_awaited()
    pyright.prepare_type_hierarchy.assert_not_awaited()


@pytest.mark.asyncio
async def test_outline_tools_reject_invalid_caller_input(tmp_path: Path) -> None:
    """Outline caller-input checks raise ToolInputError naming the parameter."""
    pyright = AsyncMock()

    with pytest.raises(ToolInputError, match="^name_pattern"):
        await navigation.get_symbol_outline(pyright, _config(tmp_path), name_pattern="(")

    with pytest.raises(ToolInputError, match="^positions"):
        await navigation.selection_range(pyright, "/repo/a.py", [])

    pyright.get_selection_range.assert_not_awaited()


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

    assert [item.name for item in result.items] == ["a", "b"]
    assert result.total_count == 2
    assert result.total_nodes == 2
    assert result.returned_nodes == 2
    assert result.truncated is False


def _outline_node(
    name: str,
    path: str,
    line: int,
    end_line: int,
    children: list[SymbolOutlineItem] | None = None,
) -> SymbolOutlineItem:
    return SymbolOutlineItem(
        name=name,
        kind="class" if children else "function",
        file_path=path,
        range=Range(start=Position(line=line, character=0), end=Position(line=end_line, character=0)),
        selection_range=Range(start=Position(line=line, character=0), end=Position(line=line, character=1)),
        children=children or [],
    )


def _outline_tree(path: str) -> list[SymbolOutlineItem]:
    """Two roots: ``A`` (1 + 4 descendants, one nested two deep) and ``B`` (1 node)."""
    inner = _outline_node("A.m1.inner", path, 2, 3)
    a = _outline_node(
        "A",
        path,
        0,
        20,
        [
            _outline_node("A.m1", path, 1, 4, [inner]),
            _outline_node("A.m2", path, 5, 8),
            _outline_node("A.m3", path, 9, 12),
        ],
    )
    b = _outline_node("B", path, 30, 31)
    return [a, b]


def _names(item: SymbolOutlineItem) -> list[str]:
    return [item.name, *(name for child in item.children for name in _names(child))]


def test_node_budget_prunes_crossing_root_depth_first() -> None:
    """max_nodes keeps a depth-first prefix of the root that crosses the budget."""
    roots = _outline_tree("/repo/m.py")

    kept, returned, truncated = _apply_node_budget(roots, 3)

    assert [_names(item) for item in kept] == [["A", "A.m1", "A.m1.inner"]]
    assert returned == 3
    assert truncated is True
    # The source tree is copied, never mutated.
    assert _names(roots[0]) == ["A", "A.m1", "A.m1.inner", "A.m2", "A.m3"]


def test_node_budget_stops_at_root_boundary_and_passes_through_when_unbounded() -> None:
    """A budget exactly covering the first root drops later roots; ample or no budget keeps all."""
    roots = _outline_tree("/repo/m.py")

    kept, returned, truncated = _apply_node_budget(roots, 5)
    assert [_names(item) for item in kept] == [["A", "A.m1", "A.m1.inner", "A.m2", "A.m3"]]
    assert (returned, truncated) == (5, True)

    assert _apply_node_budget(roots, 6)[1:] == (6, False)
    assert _apply_node_budget(roots, None)[1:] == (6, False)


@pytest.mark.asyncio
async def test_get_symbol_outline_root_limit_and_offset_report_truncation(tmp_path: Path) -> None:
    """limit counts roots, max_nodes counts nodes; both report truncation through the result."""
    module = tmp_path / "m.py"
    module.write_text("def a():\n    pass\n", encoding="utf-8")
    path = str(module)
    pyright = AsyncMock()
    pyright.get_document_symbols.side_effect = lambda _path: [
        _outline_node(name, path, line, line) for line, name in enumerate(["a", "b", "c"])
    ]

    async def _outline(**kwargs: object) -> SymbolOutlineResult:
        return await navigation.get_symbol_outline(pyright, _config(tmp_path), file_path=path, **kwargs)  # type: ignore[arg-type]

    limited = await _outline(limit=1)
    assert [item.name for item in limited.items] == ["a"]
    assert (limited.total_count, limited.returned_nodes, limited.truncated) == (3, 1, True)

    paged = await _outline(offset=1)
    assert [item.name for item in paged.items] == ["b", "c"]
    assert (paged.offset, paged.total_count, paged.truncated) == (1, 3, False)

    budgeted = await _outline(max_nodes=2)
    assert [item.name for item in budgeted.items] == ["a", "b"]
    assert (budgeted.total_nodes, budgeted.returned_nodes, budgeted.truncated) == (3, 2, True)

    whole = await _outline(max_nodes=3)
    assert (whole.returned_nodes, whole.truncated) == (3, False)


@pytest.mark.asyncio
async def test_get_symbol_outline_rejects_non_positive_max_nodes(tmp_path: Path) -> None:
    """max_nodes below one is a caller error raised before any backend call."""
    pyright = AsyncMock()

    with pytest.raises(ToolInputError, match="max_nodes"):
        await navigation.get_symbol_outline(pyright, _config(tmp_path), max_nodes=0)

    pyright.get_document_symbols.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("parameter", ["file_path", "file_paths", "root_path"])
async def test_get_symbol_outline_rejects_missing_scope(parameter: str, tmp_path: Path) -> None:
    """An explicit missing scope is a caller error, not an empty outline."""
    present = tmp_path / "present.py"
    present.write_text("def a():\n    pass\n", encoding="utf-8")
    missing = str(tmp_path / "missing")
    arguments: dict[str, object] = {
        "file_path": {"file_path": missing},
        "file_paths": {"file_paths": [str(present), missing]},
        "root_path": {"root_path": missing},
    }[parameter]
    pyright = AsyncMock()

    with pytest.raises(ToolInputError, match=parameter):
        await navigation.get_symbol_outline(pyright, _config(tmp_path), **arguments)  # type: ignore[arg-type]

    pyright.get_document_symbols.assert_not_awaited()


@pytest.mark.asyncio
async def test_find_implementations_deduplicates_results() -> None:
    """Ensure implementation results are de-duplicated and sorted."""
    pyright = AsyncMock()
    shared = _location("/repo/a.py", 1, 2)
    pyright.get_implementation.return_value = [shared, shared, _location("/repo/b.py", 0, 0)]

    result = await navigation.find_implementations(pyright, "/repo/a.py", 1, 2)

    assert [item.file_path for item in result] == ["/repo/a.py", "/repo/b.py"]


@pytest.mark.asyncio
async def test_get_declaration_and_type_definition_deduplicate() -> None:
    """Ensure declaration and type definition outputs are deduplicated."""
    pyright = AsyncMock()
    shared = _location("/repo/a.py", 1, 2)
    pyright.get_declaration.return_value = [shared, shared]
    pyright.get_type_definition.return_value = [shared, _location("/repo/b.py", 0, 0)]

    declarations = await navigation.get_declaration(pyright, "/repo/a.py", 1, 2)
    type_definitions = await navigation.get_type_definition(pyright, "/repo/a.py", 1, 2)

    assert len(declarations) == 1
    assert [item.file_path for item in type_definitions] == ["/repo/a.py", "/repo/b.py"]


@pytest.mark.asyncio
async def test_get_folding_ranges_sorted() -> None:
    """Ensure folding ranges are returned in deterministic source order."""
    pyright = AsyncMock()
    pyright.get_folding_ranges.return_value = [
        FoldingRange(start_line=10, end_line=20, kind="region"),
        FoldingRange(start_line=2, end_line=5, kind="imports"),
    ]

    result = await navigation.get_folding_ranges(pyright, "/repo/a.py")

    assert [item.start_line for item in result] == [2, 10]


@pytest.mark.asyncio
async def test_get_folding_ranges_falls_back_to_ast_when_unsupported(tmp_path: Path) -> None:
    """An LSP_UNSUPPORTED folding request degrades to AST-derived ranges."""
    sample = tmp_path / "sample.py"
    sample.write_text("def outer():\n    x = 1\n    return x\n", encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_folding_ranges.side_effect = LspFeatureUnsupportedError(
        "textDocument/foldingRange unhandled by Pyright"
    )

    result = await navigation.get_folding_ranges(pyright, str(sample))

    assert [(item.start_line, item.end_line) for item in result] == [(0, 2)]


@pytest.mark.asyncio
async def test_type_hierarchy_propagates_unsupported_without_retry(tmp_path: Path) -> None:
    """An unsupported prepareTypeHierarchy raises instead of returning a placeholder."""
    sample = tmp_path / "sample.py"
    sample.write_text("class Widget:\n    pass\n", encoding="utf-8")
    pyright = AsyncMock()
    pyright.prepare_type_hierarchy.side_effect = LspFeatureUnsupportedError(
        "textDocument/prepareTypeHierarchy unhandled by Pyright"
    )

    with pytest.raises(LspFeatureUnsupportedError) as raised:
        await navigation.type_hierarchy(pyright, str(sample), 0, 0)

    assert raised.value.code == "LSP_UNSUPPORTED"
    pyright.prepare_type_hierarchy.assert_awaited_once()


@pytest.mark.asyncio
async def test_type_hierarchy_collects_depth() -> None:
    """Ensure type hierarchy traverses supertypes and subtypes to requested depth."""
    pyright = AsyncMock()
    root = TypeHierarchyItem(
        name="Widget",
        kind="class",
        file_path="/repo/a.py",
        range=Range(start=Position(line=1, character=0), end=Position(line=1, character=6)),
    )
    base = TypeHierarchyItem(
        name="BaseWidget",
        kind="class",
        file_path="/repo/base.py",
        range=Range(start=Position(line=1, character=0), end=Position(line=1, character=10)),
    )
    derived = TypeHierarchyItem(
        name="SpecialWidget",
        kind="class",
        file_path="/repo/derived.py",
        range=Range(start=Position(line=1, character=0), end=Position(line=1, character=13)),
    )
    pyright.prepare_type_hierarchy.return_value = [root]
    pyright.get_supertypes.return_value = [base]
    pyright.get_subtypes.return_value = [derived]

    result = await navigation.type_hierarchy(pyright, "/repo/a.py", 1, 0, depth=2)

    assert result.item.name == "Widget"
    assert [item.name for item in result.supertypes] == ["BaseWidget"]
    assert [item.name for item in result.subtypes] == ["SpecialWidget"]


@pytest.mark.asyncio
async def test_selection_range_passthrough() -> None:
    """Ensure selection range results are delegated from Pyright backend."""
    pyright = AsyncMock()
    expected = [
        SelectionRangeResult(
            position=Position(line=1, character=4),
            ranges=[Range(start=Position(line=1, character=4), end=Position(line=1, character=10))],
        )
    ]
    pyright.get_selection_range.return_value = expected

    result = await navigation.selection_range(pyright, "/repo/a.py", [Position(line=1, character=4)])

    assert result == expected


# ── PR 3-B: Invalid-input / failure-path unit tests ──


@pytest.mark.asyncio
async def test_goto_definition_empty_result() -> None:
    """When both Pyright and Jedi return nothing, result is empty list."""
    pyright = AsyncMock()
    jedi = AsyncMock()
    pyright.get_definition.return_value = []
    jedi.goto_definition.side_effect = RuntimeError("jedi crashed")

    result = await navigation.goto_definition(pyright, jedi, "/repo/a.py", 0, 0)

    assert result == []
