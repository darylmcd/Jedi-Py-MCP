"""Shared pytest fixtures for unit and integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

collect_ignore_glob = ["integration/fixtures/**"]


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace with a sample Python source file."""
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    sample_file = src_dir / "sample.py"
    sample_file.write_text(
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def sample_python_file(tmp_workspace: Path) -> Path:
    """Return the path to the sample Python source file."""
    return tmp_workspace / "src" / "sample.py"
