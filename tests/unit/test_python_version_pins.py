"""Regression: keep Python version pins in sync across config files.

If you bump one of the four pins below, bump all of them in the same change:
    pyproject.toml [project] requires-python
    pyproject.toml [tool.ruff] target-version
    pyproject.toml [tool.mypy] python_version
    pyrightconfig.json pythonVersion
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _normalize(raw: str) -> tuple[int, int]:
    """Return (major, minor) parsed from any of the supported pin formats.

    Accepts: ``"3.14"``, ``">=3.14"``, ``"py314"``, ``"cp314"``.
    """
    dotted = re.search(r"(\d+)\.(\d+)", raw)
    if dotted is not None:
        return int(dotted.group(1)), int(dotted.group(2))
    compact = re.search(r"py(\d)(\d+)\b", raw)
    if compact is not None:
        return int(compact.group(1)), int(compact.group(2))
    raise AssertionError(f"unrecognized python version pin: {raw!r}")


def test_python_version_pins_agree() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pyright = json.loads((REPO_ROOT / "pyrightconfig.json").read_text(encoding="utf-8"))

    pins = {
        "pyproject.requires-python": _normalize(pyproject["project"]["requires-python"]),
        "pyproject.ruff.target-version": _normalize(pyproject["tool"]["ruff"]["target-version"]),
        "pyproject.mypy.python_version": _normalize(pyproject["tool"]["mypy"]["python_version"]),
        "pyrightconfig.pythonVersion": _normalize(pyright["pythonVersion"]),
    }

    distinct = set(pins.values())
    assert len(distinct) == 1, (
        f"Python version pins disagree across config files: {pins}. "
        "Bump all four together when raising the floor."
    )
