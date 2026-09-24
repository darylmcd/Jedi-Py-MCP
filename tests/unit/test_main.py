"""Unit tests for the command-line entry point."""

from __future__ import annotations

import io
import json
import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from python_refactor_mcp import __main__ as cli
from python_refactor_mcp.errors import PyrightError
from python_refactor_mcp.tool_runtime import _translate_backend_error

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


def test_main_rejects_missing_workspace_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An explicitly supplied missing workspace root fails before startup."""
    missing = tmp_path / "missing"
    monkeypatch.setattr(sys, "argv", ["python-refactor-mcp", str(missing)])

    with pytest.raises(SystemExit, match="Workspace root does not exist or is not a directory"):
        cli.main()
