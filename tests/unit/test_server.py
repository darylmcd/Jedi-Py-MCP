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
async def test_server_registers_expected_tool_surface() -> None:
    """Ensure the current MCP tool surface is registered on the MCP instance."""
    tools = await server.mcp.list_tools()
    assert len(tools) == 100
    assert "convert_to_dataclass" in {tool.name for tool in tools}
    assert "check_type_stub_freshness" in {tool.name for tool in tools}
    assert all("ctx" not in tool.input_schema.get("properties", {}) for tool in tools)


@pytest.mark.asyncio
async def test_position_based_tools_document_zero_based_convention() -> None:
    """Every tool taking caller-supplied positions states the 0-based convention.

    Data-driven and drift-proof, mirroring the tool-count gate above: it
    enumerates the live tool surface and selects every tool whose input schema
    exposes a caller-supplied position directly as ``line``/``start_line`` or
    indirectly through the canonical ``Position``/``SymbolAnchor`` models.
    Any future position tool is auto-covered.
    """
    tools = await server.mcp.list_tools()

    def _contains_position_ref(value: object) -> bool:
        if isinstance(value, dict):
            ref = value.get("$ref")
            return (
                isinstance(ref, str)
                and (ref.endswith("/Position") or ref.endswith("/SymbolAnchor"))
            ) or any(_contains_position_ref(child) for child in value.values())
        if isinstance(value, list):
            return any(_contains_position_ref(child) for child in value)
        return False

    position_tools = [
        tool
        for tool in tools
        if {"line", "start_line"} & set(tool.input_schema.get("properties", {}))
        or _contains_position_ref(tool.input_schema.get("properties", {}))
    ]
    # Guard against the selector silently matching nothing (e.g. a schema-shape
    # change), which would make the assertion below vacuously pass.
    assert position_tools, "expected at least one position-based tool in the surface"
    assert {"selection_range", "test_impact_select"} <= {tool.name for tool in position_tools}

    missing = [
        tool.name
        for tool in position_tools
        if POSITION_CONVENTION_PHRASE not in (tool.description or "")
    ]
    assert not missing, (
        f"{len(missing)} position-based tool description(s) missing the 0-based "
        f"convention phrase: {sorted(missing)}"
    )
