"""Server configuration discovery for workspace-specific settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeGuard

from python_refactor_mcp.errors import ConfigError
from python_refactor_mcp.util.python_detect import detect_python

ToolProfile = Literal["analysis", "refactoring"]

TOOL_PROFILE_ENV = "PYTHON_REFACTOR_MCP_TOOL_PROFILE"
TOOL_PROFILES: tuple[ToolProfile, ...] = ("analysis", "refactoring")
DEFAULT_TOOL_PROFILE: ToolProfile = "refactoring"


def _is_tool_profile(value: str) -> TypeGuard[ToolProfile]:
    """Narrow a normalized string to the supported profile literal."""
    return value in TOOL_PROFILES


def discover_tool_profile(value: str | None = None) -> ToolProfile:
    """Return the configured advertised tool profile or fail closed."""
    raw = os.environ.get(TOOL_PROFILE_ENV) if value is None else value
    normalized = raw.strip().lower() if raw is not None else DEFAULT_TOOL_PROFILE
    if not _is_tool_profile(normalized):
        choices = ", ".join(TOOL_PROFILES)
        raise ConfigError(f"Invalid {TOOL_PROFILE_ENV} value {raw!r}; expected one of: {choices}")
    return normalized


def discover_max_workspaces(value: str | None = None) -> int:
    """Return the positive workspace cache limit with a stable config error."""
    raw = os.environ.get("MAX_WORKSPACES", "3") if value is None else value
    try:
        limit = int(raw)
    except ValueError as exc:
        raise ConfigError(f"Invalid MAX_WORKSPACES value {raw!r}; expected a positive integer") from exc
    if limit <= 0:
        raise ConfigError(f"Invalid MAX_WORKSPACES value {raw!r}; expected a positive integer")
    return limit


@dataclass(slots=True)
class ServerConfig:
    """Runtime configuration for the MCP server and backends."""

    workspace_root: Path
    python_executable: Path
    venv_path: Path | None
    pyright_executable: str
    pyrightconfig_path: Path | None
    rope_prefs: dict[str, object]


def discover_config(workspace_root: Path) -> ServerConfig:
    """Discover server configuration values for the provided workspace root."""
    # Use abspath instead of resolve() to avoid following symlinks which would
    # create path mismatches with client-provided symlink paths.
    root = Path(os.path.abspath(workspace_root))
    if not root.exists() or not root.is_dir():
        raise ConfigError(f"Workspace root does not exist or is not a directory: {root}")

    python_executable, venv_path = detect_python(root)

    pyright_executable = os.environ.get("PYRIGHT_LANGSERVER", "pyright-langserver")
    pyrightconfig_candidate = root / "pyrightconfig.json"
    pyrightconfig_path = pyrightconfig_candidate if pyrightconfig_candidate.exists() else None

    rope_prefs: dict[str, object] = {
        "save_objectdb": False,
        "automatic_soa": True,
        "soa_followed_calls": 0,
        "validate_objectdb": False,
    }

    return ServerConfig(
        workspace_root=root,
        python_executable=python_executable,
        venv_path=venv_path,
        pyright_executable=pyright_executable,
        pyrightconfig_path=pyrightconfig_path,
        rope_prefs=rope_prefs,
    )
