"""Unit tests for server shell behavior."""

from __future__ import annotations

import pytest

from python_refactor_mcp import server

# Shared 0-based position convention sentence. Every position-based tool
# description must embed this verbatim; this constant is the single source of
# truth the gate below asserts against. Keep it in sync with the wording in
# ``python_refactor_mcp.models.Position`` ("0-based line and character offset").
POSITION_CONVENTION_PHRASE = "Positions are 0-based (line and character offsets, LSP convention)."


@pytest.mark.asyncio
async def test_server_registers_all_stage_one_tools() -> None:
    """Ensure the expanded MCP tool surface is registered on the MCP instance."""
    tools = await server.mcp.list_tools()
    assert len(tools) == 98
    assert all("ctx" not in tool.inputSchema.get("properties", {}) for tool in tools)


@pytest.mark.asyncio
async def test_position_based_tools_document_zero_based_convention() -> None:
    """Every tool taking caller-supplied positions states the 0-based convention.

    Data-driven and drift-proof, mirroring the tool-count gate above: it
    enumerates the live tool surface and selects every tool whose input schema
    exposes a caller-supplied position parameter directly as ``line``/``character``
    (or the ``start_line``/``start_character`` range form). Any future
    line/character-shaped position tool is auto-covered — its description must
    carry :data:`POSITION_CONVENTION_PHRASE` or this gate fails. Tools that nest
    positions inside a ``Position`` object (e.g. ``selection_range`` with
    ``positions: list[Position]``) are NOT matched by this selector; their
    callers learn the convention from the ``Position`` model's own description.
    Extending the phrase + selector to those is tracked separately.
    """
    tools = await server.mcp.list_tools()
    position_tools = [
        tool
        for tool in tools
        if {"line", "start_line"} & set(tool.inputSchema.get("properties", {}))
    ]
    # Guard against the selector silently matching nothing (e.g. a schema-shape
    # change), which would make the assertion below vacuously pass.
    assert position_tools, "expected at least one position-based tool in the surface"

    missing = [
        tool.name
        for tool in position_tools
        if POSITION_CONVENTION_PHRASE not in (tool.description or "")
    ]
    assert not missing, (
        f"{len(missing)} position-based tool description(s) missing the 0-based "
        f"convention phrase: {sorted(missing)}"
    )
