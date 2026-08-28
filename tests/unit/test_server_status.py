"""Unit tests for the server_status tool and its status builder."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from python_refactor_mcp import server
from python_refactor_mcp.server import MultiWorkspaceContext, _build_server_status
from python_refactor_mcp.workspace_registry import WorkspaceBackends, WorkspaceRegistry


def _backends(root: Path, *, initialized: bool, pyright_up: bool, jedi: bool, rope: bool) -> WorkspaceBackends:
    """Build a WorkspaceBackends with mocked liveness signals."""
    config = MagicMock()
    config.workspace_root = root
    config.python_executable = root / ".venv" / "bin" / "python"
    config.pyright_executable = "pyright-langserver"

    pyright = MagicMock()
    pyright.is_running = pyright_up
    jedi_backend = MagicMock()
    jedi_backend.is_ready = jedi
    rope_backend = MagicMock()
    rope_backend.is_ready = rope

    backends = WorkspaceBackends(config=config, pyright=pyright, jedi=jedi_backend, rope=rope_backend)
    backends._initialized = initialized
    return backends


def test_status_empty_registry_is_degraded() -> None:
    """No loaded workspaces -> degraded, no active workspaces."""
    registry = WorkspaceRegistry()
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)

    status = _build_server_status(multi_ctx)

    assert status.degraded is True
    assert status.active_workspaces == []
    assert status.known_roots == []
    assert status.cli_workspace_root is None
    assert status.version == server.__version__


def test_status_reports_per_backend_liveness(tmp_path: Path) -> None:
    """A healthy workspace surfaces per-backend booleans and is not degraded."""
    registry = WorkspaceRegistry()
    root = tmp_path / "ws"
    registry._workspaces[root] = _backends(root, initialized=True, pyright_up=True, jedi=True, rope=True)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=root)

    status = _build_server_status(multi_ctx)

    assert status.degraded is False
    assert len(status.active_workspaces) == 1
    live = status.active_workspaces[0]
    assert live.workspace_root == str(root)
    assert live.initialized is True
    assert live.pyright_running is True
    assert live.jedi_ready is True
    assert live.rope_ready is True
    assert live.python_executable.endswith("python")
    assert status.cli_workspace_root == str(root)


def test_status_degraded_when_pyright_down(tmp_path: Path) -> None:
    """Pyright subprocess down -> degraded even though the workspace is loaded."""
    registry = WorkspaceRegistry()
    root = tmp_path / "ws"
    registry._workspaces[root] = _backends(root, initialized=True, pyright_up=False, jedi=True, rope=True)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)

    status = _build_server_status(multi_ctx)

    assert status.degraded is True
    assert status.active_workspaces[0].pyright_running is False
    assert status.active_workspaces[0].jedi_ready is True


@pytest.mark.asyncio
async def test_server_status_registered_and_readonly() -> None:
    """server_status is registered on the MCP instance as a read-only tool."""
    tools = {tool.name: tool for tool in await server.mcp.list_tools()}
    assert "server_status" in tools
    assert "ctx" not in tools["server_status"].input_schema.get("properties", {})
