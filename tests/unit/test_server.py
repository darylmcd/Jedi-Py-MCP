"""Unit tests for server shell behavior."""

from __future__ import annotations

import pytest

from python_refactor_mcp import server


@pytest.mark.asyncio
async def test_server_registers_all_stage_one_tools() -> None:
    """Ensure the expanded MCP tool surface is registered on the MCP instance."""
    tools = await server.mcp.list_tools()
    assert len(tools) == 89
    assert all("ctx" not in tool.inputSchema.get("properties", {}) for tool in tools)
