"""Regression: every Python file in ``src/`` is space-indented (no tabs).

This guards against the historical drift where ``server.py`` was tab-indented
while every other module used 4-space indentation. ``.editorconfig`` and the
``[tool.ruff.format] indent-style = "space"`` pin in ``pyproject.toml`` document
the intent; this test enforces it in CI.
"""

from __future__ import annotations

from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def test_no_tab_indented_python_files_in_src() -> None:
    offenders: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(line.startswith("\t") for line in text.splitlines()):
            offenders.append(str(path.relative_to(SRC_ROOT.parent)))
    assert offenders == [], (
        "Tab-indented Python files found in src/ — convert to 4-space indent "
        "and re-run `ruff format`:\n  " + "\n  ".join(offenders)
    )
