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


_TEST_DIRECTORY_NAMES: frozenset[str] = frozenset({"tests", "test"})


def is_test_file(path: Path, root: Path | None = None) -> bool:
    """Return whether *path* is a test module.

    A module is a test file when its name is ``test_*``, ``*_test.py`` or
    ``conftest.py``, or when any directory between *root* and the file is named
    ``tests`` or ``test`` (compared with ``os.path.normcase``, so case-insensitive
    on Windows only). Only components below *root* count: a workspace that itself
    lives under a ``tests`` directory is not wholly a test tree. Only the filename
    rule applies when *root* is ``None``, when *path* is outside *root* (including
    a symlink that resolves outside it), or when it cannot be resolved.
    """
    name = path.name
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return True
    if root is None:
        return False
    try:
        relative_parent = path.resolve().relative_to(root.resolve()).parent
    except (ValueError, OSError):
        return False
    return any(os.path.normcase(part) in _TEST_DIRECTORY_NAMES for part in relative_parent.parts)
