"""Filtered file iteration with sensible directory exclusions."""

from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        "node_modules",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".eggs",
    }
)


def python_files(
    root: Path,
    exclude_dirs: set[str] | None = None,
) -> list[Path]:
    """Return Python files below *root* in stable order, skipping excluded directories.

    Uses ``os.walk`` with top-down pruning so excluded subtrees are never
    entered.  Falls back to ``_DEFAULT_EXCLUDE_DIRS`` when *exclude_dirs* is
    ``None``.
    """
    effective = exclude_dirs if exclude_dirs is not None else _DEFAULT_EXCLUDE_DIRS
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place so os.walk skips them.
        dirnames[:] = [d for d in dirnames if d not in effective]
        for filename in filenames:
            if filename.endswith(".py"):
                full_path = Path(dirpath) / filename
                if full_path.is_file():
                    results.append(full_path)
    return sorted(results)
