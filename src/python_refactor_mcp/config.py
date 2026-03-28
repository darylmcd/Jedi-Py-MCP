"""Server configuration discovery for workspace-specific settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from python_refactor_mcp.errors import ConfigError
from python_refactor_mcp.util.python_detect import detect_python


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
