"""Unit tests for the command-line entry point."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from python_refactor_mcp import __main__ as cli
from python_refactor_mcp import server
from python_refactor_mcp.errors import AmbiguousWorkspaceError, PyrightError
from python_refactor_mcp.tool_runtime import _translate_backend_error
from python_refactor_mcp.workspace_registry import WorkspaceRegistry

_PACKAGE_LOGGER = logging.getLogger("python_refactor_mcp")


def _diagnostics_handlers() -> list[logging.Handler]:
    return [handler for handler in _PACKAGE_LOGGER.handlers if isinstance(handler, cli.StderrDiagnosticsHandler)]


@pytest.fixture(autouse=True)
def _remove_installed_handlers() -> Iterator[None]:
    """Keep the package logger handler-free and propagating across tests that call ``main()``."""
    propagate = _PACKAGE_LOGGER.propagate
    yield
    for handler in _diagnostics_handlers():
        _PACKAGE_LOGGER.removeHandler(handler)
    _PACKAGE_LOGGER.propagate = propagate


def _raise_backend_failure(secret_path: str) -> PyrightError:
    try:
        try:
            raise OSError(f"{secret_path}: provider exploded")
        except OSError as cause:
            raise PyrightError(f"payload {secret_path}") from cause
    except PyrightError as exc:
        return exc


def test_main_stderr_backend_failure_line_carries_structured_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A backend failure logged after startup shows its id, types, and locations on stderr only."""
    monkeypatch.setattr(cli, "run_server", lambda _root: None)
    monkeypatch.setattr(sys, "argv", ["python-refactor-mcp"])
    # Stand-in for the bare ``%(message)s`` root handler the MCP SDK installs via basicConfig.
    root_stream = io.StringIO()
    root_handler = logging.StreamHandler(root_stream)
    logging.getLogger().addHandler(root_handler)
    try:
        cli.main()
        secret_path = "/home/private/workspace/module.py"

        tool_error = _translate_backend_error(_raise_backend_failure(secret_path), "find_references")
    finally:
        logging.getLogger().removeHandler(root_handler)

    assert root_stream.getvalue() == ""
    captured = capsys.readouterr()
    assert captured.out == ""
    lines = [line for line in captured.err.splitlines() if "Backend failure" in line]
    assert len(lines) == 1
    line = lines[0]
    failure_id = str(tool_error).rsplit("Failure ID: ", 1)[1].rstrip(".")
    assert f"failure_id={json.dumps(failure_id)}" in line
    assert ("exception_types=" + json.dumps(["python_refactor_mcp.errors.PyrightError", "builtins.OSError"])) in line
    locations = json.loads(line.split("traceback_locations=", 1)[1])
    assert locations
    assert all(location.startswith("_raise_backend_failure:") for location in locations)
    assert "private" not in captured.err
    assert "payload" not in captured.err


def test_main_installs_stderr_diagnostics_handler_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated startup does not stack duplicate stderr handlers."""
    monkeypatch.setattr(cli, "run_server", lambda _root: None)
    monkeypatch.setattr(sys, "argv", ["python-refactor-mcp"])

    cli.main()
    cli.main()

    assert len(_diagnostics_handlers()) == 1


def test_formatter_leaves_unrelated_records_and_extras_untouched() -> None:
    """Only the whitelisted backend-failure keys are appended; other extras never render."""
    formatter = cli.BackendFailureFormatter()
    record = logging.LogRecord("python_refactor_mcp.x", logging.WARNING, __file__, 1, "plain %s", ("msg",), None)
    record.failure_id = "abc"
    assert formatter.format(record) == "WARNING python_refactor_mcp.x: plain msg"

    failure = logging.LogRecord("python_refactor_mcp.server", logging.ERROR, __file__, 1, "Backend failure", (), None)
    failure.event = "tool_backend_failure"
    failure.failure_id = "abc"
    failure.request_payload = "/secret/path"
    rendered = formatter.format(failure)
    assert 'failure_id="abc"' in rendered
    assert "secret" not in rendered
    assert "exception_types" not in rendered


def test_main_starts_cold_when_workspace_root_is_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    """An omitted workspace root starts the multi-workspace server cold."""
    started_with: list[str | None] = []
    monkeypatch.setattr(cli, "run_server", started_with.append)
    monkeypatch.setattr(sys, "argv", ["python-refactor-mcp"])

    cli.main()

    assert started_with == [None]


def test_main_prewarms_resolved_workspace_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A supplied workspace root is resolved before the server starts."""
    started_with: list[str | None] = []
    monkeypatch.setattr(cli, "run_server", started_with.append)
    monkeypatch.setattr(sys, "argv", ["python-refactor-mcp", str(tmp_path)])

    cli.main()

    assert started_with == [str(tmp_path.resolve())]


@pytest.mark.asyncio
async def test_lifespan_prewarms_the_cli_root_without_selecting_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The startup pre-warm starts the CLI workspace but leaves it unselected for path-less calls."""
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()

    with (
        patch(
            "python_refactor_mcp.workspace_registry.discover_config",
            side_effect=lambda root: SimpleNamespace(workspace_root=root),
        ),
        patch("python_refactor_mcp.workspace_registry.PyrightLSPClient", side_effect=lambda _c: AsyncMock()),
        patch("python_refactor_mcp.workspace_registry.JediBackend"),
        patch("python_refactor_mcp.workspace_registry.RopeBackend"),
    ):
        async with server.workspace_lifespan(project.resolve())(MagicMock()) as multi_ctx:
            (warmed,) = multi_ctx.registry.active_backends()
            assert warmed.config.workspace_root == project.resolve()
            assert warmed.selected is False
            assert multi_ctx.cli_workspace_root == project.resolve()
            with pytest.raises(AmbiguousWorkspaceError, match="pre-warmed, not selected"):
                multi_ctx.registry.implicit_workspace()


@pytest.mark.asyncio
@pytest.mark.parametrize("step", ["set_roots", "prewarm"])
@pytest.mark.parametrize("failure", [RuntimeError("boom"), asyncio.CancelledError()], ids=["error", "cancelled"])
async def test_lifespan_shuts_the_registry_down_when_startup_fails(
    tmp_path: Path, step: str, failure: BaseException
) -> None:
    """A failure or cancellation in any startup step still runs registry teardown."""
    shutdowns: list[WorkspaceRegistry] = []

    async def record_shutdown(self: WorkspaceRegistry) -> None:
        shutdowns.append(self)

    with (
        patch.object(WorkspaceRegistry, step, side_effect=failure),
        patch.object(WorkspaceRegistry, "shutdown_all", record_shutdown),
        pytest.raises(type(failure)),
    ):
        async with server.workspace_lifespan(tmp_path)(MagicMock()):
            pytest.fail("startup must not reach the yield")

    assert len(shutdowns) == 1


@pytest.mark.asyncio
async def test_servers_built_with_different_roots_do_not_share_state(tmp_path: Path) -> None:
    """Each server's lifespan carries its own root and registry; no module global holds the root."""
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()

    with patch.object(WorkspaceRegistry, "prewarm", AsyncMock()):
        async with (
            server.workspace_lifespan(root_a)(MagicMock()) as ctx_a,
            server.workspace_lifespan(root_b)(MagicMock()) as ctx_b,
        ):
            assert ctx_a.cli_workspace_root == root_a
            assert ctx_b.cli_workspace_root == root_b
            assert ctx_a.registry is not ctx_b.registry
            assert ctx_a.registry.get_known_roots() == [root_a.resolve()]
            assert ctx_b.registry.get_known_roots() == [root_b.resolve()]
    assert not hasattr(server, "_workspace_root")
    assert server.build_server(root_a) is not server.build_server(root_a)


@pytest.mark.parametrize("given", [None, "root"])
def test_run_server_builds_the_server_with_the_resolved_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, given: str | None
) -> None:
    """run_server hands the resolved CLI root (or None) to build_server and runs that server."""
    built: list[Path | None] = []
    runner = MagicMock()

    def fake_build(root: Path | None = None) -> MagicMock:
        built.append(root)
        return runner

    monkeypatch.setattr(server, "build_server", fake_build)
    server.run_server(str(tmp_path) if given else None)

    assert built == [tmp_path.resolve() if given else None]
    runner.run.assert_called_once_with()


def test_main_rejects_missing_workspace_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An explicitly supplied missing workspace root fails before startup."""
    missing = tmp_path / "missing"
    monkeypatch.setattr(sys, "argv", ["python-refactor-mcp", str(missing)])

    with pytest.raises(SystemExit, match="Workspace root does not exist or is not a directory"):
        cli.main()
