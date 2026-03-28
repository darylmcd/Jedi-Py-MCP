"""Python executable detection for workspace environments."""

from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path

from python_refactor_mcp.errors import ConfigError


def _venv_python_executable(venv_path: Path) -> Path:
    """Return the Python executable path for a virtual environment."""
    scripts_dir = "Scripts" if os.name == "nt" else "bin"
    exe_name = "python.exe" if os.name == "nt" else "python"
    return venv_path / scripts_dir / exe_name


def detect_python(workspace_root: Path) -> tuple[Path, Path | None]:
    """Resolve the Python executable and optional venv path for a workspace.

    Searches in order:
    1. .venv/ or venv/ directories
    2. pyproject.toml Poetry virtualenvs.path
    3. VIRTUAL_ENV environment variable
    4. python3 on PATH
    5. python on PATH

    Returns (python_executable, venv_path_or_None).
    Raises ConfigError if no Python executable is found.
    """
    for candidate_name in (".venv", "venv"):
        candidate = workspace_root / candidate_name
        python_path = _venv_python_executable(candidate)
        if candidate.is_dir() and python_path.exists():
            return python_path, candidate

    pyproject_path = workspace_root / "pyproject.toml"
    if pyproject_path.exists():
        try:
            pyproject_data: dict[str, object] = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError):
            pyproject_data = {}
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
