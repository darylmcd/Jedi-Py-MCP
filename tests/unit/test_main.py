"""Unit tests for the command-line entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from python_refactor_mcp import __main__ as cli


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
