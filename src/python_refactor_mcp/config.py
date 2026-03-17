"""Server configuration discovery for workspace-specific settings."""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

from python_refactor_mcp.errors import ConfigError


@dataclass(slots=True)
class ServerConfig:
    """Runtime configuration for the MCP server and backends."""

    workspace_root: Path
    python_executable: Path
    venv_path: Path | None
    pyright_executable: str
    pyrightconfig_path: Path | None
    rope_prefs: dict[str, object]


def _venv_python_executable(venv_path: Path) -> Path:
    """Return the Python executable path for a virtual environment."""
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    exe_name = "python.exe" if os.name == "nt" else "python"
    return venv_path / scripts_dir / exe_name


def _detect_python_from_workspace(workspace_root: Path) -> tuple[Path, Path | None]:
    """Resolve the Python executable and optional venv path for a workspace."""
    for candidate_name in (".venv", "venv"):
        candidate = workspace_root / candidate_name
        python_path = _venv_python_executable(candidate)
        if candidate.is_dir() and python_path.exists():
            return python_path, candidate

    pyproject_path = workspace_root / "pyproject.toml"
    if pyproject_path.exists():
        pyproject_data: dict[str, object] = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        tool_section = pyproject_data.get("tool")
        if isinstance(tool_section, dict):
            poetry_section = tool_section.get("poetry")
            if isinstance(poetry_section, dict):
                venv_section = poetry_section.get("virtualenvs")
                if isinstance(venv_section, dict):
                    path_value = venv_section.get("path")
                    if isinstance(path_value, str):
                        candidate = Path(path_value)
                        if not candidate.is_absolute():
                            candidate = workspace_root / candidate
                        python_path = _venv_python_executable(candidate)
                        if candidate.is_dir() and python_path.exists():
                            return python_path, candidate

    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env is not None:
        candidate = Path(virtual_env)
        python_path = _venv_python_executable(candidate)
        if candidate.is_dir() and python_path.exists():
            return python_path, candidate

    python3_path = shutil.which("python3")
    if python3_path is not None:
        return Path(python3_path), None

    python_binary = shutil.which("python")
    if python_binary is not None:
        return Path(python_binary), None

    raise ConfigError("Unable to find a Python executable via venv, VIRTUAL_ENV, python3, or python.")


def discover_config(workspace_root: Path) -> ServerConfig:
    """Discover server configuration values for the provided workspace root."""
    root = workspace_root.resolve()
    if not root.exists() or not root.is_dir():
        raise ConfigError(f"Workspace root does not exist or is not a directory: {root}")

    python_executable, venv_path = _detect_python_from_workspace(root)

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
