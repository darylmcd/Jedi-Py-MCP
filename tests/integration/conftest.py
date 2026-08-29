"""Integration fixtures for end-to-end MCP server tests."""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.fixture
def sample_workspace(tmp_path: Path) -> Path:
    """Copy fixture project into a temporary workspace and return its path."""
    fixture_root = Path(__file__).resolve().parent / "fixtures" / "sample_project"
    workspace_root = tmp_path / "sample_project"
    shutil.copytree(fixture_root, workspace_root)
    return workspace_root


@pytest_asyncio.fixture
async def mcp_session(
    request: pytest.FixtureRequest,
    sample_workspace: Path,
) -> AsyncIterator[ClientSession]:
    """Start the requested MCP profile over stdio and yield a client session."""
    if os.environ.get("RUN_MCP_INTEGRATION") != "1":
        pytest.skip(
            "Run ./scripts/test-integration.ps1 or set RUN_MCP_INTEGRATION=1 "
            "to run MCP stdio integration tests."
        )

    repo_root = Path(__file__).resolve().parents[2]
    python_executable = repo_root / ".venv" / "Scripts" / "python.exe"
    if not python_executable.exists():
        pytest.skip("Virtual environment python executable is not available.")

    scripts_dir = python_executable.parent
    pyright_cmd = scripts_dir / "pyright-langserver.cmd"
    pyright_exe = scripts_dir / "pyright-langserver.exe"
    if pyright_cmd.exists():
        pyright_path = str(pyright_cmd)
    elif pyright_exe.exists():
        pyright_path = str(pyright_exe)
    else:
        pytest.skip("pyright-langserver is unavailable for integration tests.")

    tool_profile = getattr(request, "param", "refactoring")
    if tool_profile not in {"analysis", "refactoring"}:
        raise ValueError(f"Unknown integration-test tool profile: {tool_profile!r}")

    server_env = {
        **os.environ,
        "PYTHONPATH": str(repo_root / "src"),
        "PYTHON_REFACTOR_MCP_TOOL_PROFILE": tool_profile,
        "PYRIGHT_LANGSERVER": pyright_path,
        "PATH": str(scripts_dir) + os.pathsep + os.environ.get("PATH", ""),
    }

    server_params = StdioServerParameters(
        command=str(python_executable),
        args=["-m", "python_refactor_mcp", str(sample_workspace)],
        cwd=str(repo_root),
        env=server_env,
    )

    ready: asyncio.Future[ClientSession] = asyncio.get_running_loop().create_future()
    stop = asyncio.Event()

    async def own_session() -> None:
        """Keep AnyIO cancel-scope entry and exit in one asyncio task."""
        try:
            async with stdio_client(server_params) as (read_stream, write_stream), ClientSession(
                read_stream,
                write_stream,
            ) as session:
                await session.initialize()
                ready.set_result(session)
                await stop.wait()
        except BaseException as exc:
            if not ready.done():
                ready.set_exception(exc)
                return
            raise

    owner_task = asyncio.create_task(own_session(), name="mcp-test-session-owner")
    try:
        yield await ready
    finally:
        stop.set()
        await owner_task
