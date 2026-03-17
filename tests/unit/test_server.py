"""Unit tests for server shell behavior."""

from __future__ import annotations

import pytest

from python_refactor_mcp import server


@pytest.mark.asyncio
async def test_server_registers_all_stage_one_tools() -> None:
    """Ensure all 15 Stage 1 tools are registered on the MCP instance."""
    tools = await server.mcp.list_tools()
    assert len(tools) == 15
    assert all("ctx" not in tool.inputSchema.get("properties", {}) for tool in tools)
