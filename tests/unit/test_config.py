"""Unit tests for configuration discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from python_refactor_mcp.config import (
    DEFAULT_TOOL_PROFILE,
    TOOL_PROFILE_ENV,
    discover_config,
    discover_max_workspaces,
    discover_tool_profile,
)
from python_refactor_mcp.errors import ConfigError


def test_discover_config_detects_local_venv(tmp_path: Path) -> None:
    """Prefer local .venv interpreter when present."""
    workspace = tmp_path / "workspace"
    venv_python = workspace / ".venv" / "Scripts" / "python.exe"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text("", encoding="utf-8")

    config = discover_config(workspace)
    assert config.venv_path is not None
    assert config.python_executable == venv_python


def test_discover_config_detects_pyrightconfig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve pyrightconfig path and fallback Python from PATH."""
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "pyrightconfig.json").write_text("{}", encoding="utf-8")

    fake_python = workspace / "python.exe"
    fake_python.write_text("", encoding="utf-8")

    def which_override(command: str) -> str | None:
        """Return only the fake python path for the python command."""
        if command == "python":
            return str(fake_python)
        return None

    monkeypatch.setattr("python_refactor_mcp.util.python_detect.shutil.which", which_override)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)

    config = discover_config(workspace)
    assert config.pyrightconfig_path == workspace / "pyrightconfig.json"
    assert config.python_executable == fake_python


def test_discover_config_invalid_workspace_raises(tmp_path: Path) -> None:
    """Raise ConfigError for non-directory workspace roots."""
    missing_workspace = tmp_path / "missing"
    with pytest.raises(ConfigError):
        discover_config(missing_workspace)


def test_discover_tool_profile_defaults_to_refactoring(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default server surface is the curated refactoring profile."""
    monkeypatch.delenv(TOOL_PROFILE_ENV, raising=False)
    assert discover_tool_profile() == DEFAULT_TOOL_PROFILE == "refactoring"


def test_discover_tool_profile_normalizes_explicit_value() -> None:
    """Profile selection is whitespace- and case-insensitive."""
    assert discover_tool_profile(" Analysis ") == "analysis"


def test_discover_tool_profile_rejects_unknown_value() -> None:
    """An unknown profile fails closed with the configuration key."""
    with pytest.raises(ConfigError, match=TOOL_PROFILE_ENV):
        discover_tool_profile("full")


@pytest.mark.parametrize("value", ["0", "-1", "many"])
def test_discover_max_workspaces_rejects_invalid_values(value: str) -> None:
    """The workspace cache limit reports a stable config error."""
    with pytest.raises(ConfigError, match="MAX_WORKSPACES"):
        discover_max_workspaces(value)


def test_discover_max_workspaces_accepts_positive_integer() -> None:
    """A positive workspace cache limit is returned unchanged."""
    assert discover_max_workspaces("5") == 5
