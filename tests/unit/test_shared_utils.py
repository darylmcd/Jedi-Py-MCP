"""Unit tests for consolidated shared utilities."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from python_refactor_mcp.models import Diagnostic, Location, Position, Range
from python_refactor_mcp.util.file_filter import python_files
from python_refactor_mcp.util.paths import normalize_path, path_to_uri, uri_to_path
from python_refactor_mcp.util.shared import apply_limit, diagnostic_key, location_key

# --- apply_limit ---


class TestApplyLimit:
    """Tests for the shared apply_limit helper."""

    def test_none_limit_returns_all(self) -> None:
        items = [1, 2, 3]
        result, truncated = apply_limit(items, None)
        assert result == [1, 2, 3]
        assert truncated is False

    def test_limit_greater_than_length(self) -> None:
        items = [1, 2, 3]
        result, truncated = apply_limit(items, 10)
        assert result == [1, 2, 3]
        assert truncated is False

    def test_limit_equal_to_length(self) -> None:
        items = [1, 2, 3]
        result, truncated = apply_limit(items, 3)
        assert result == [1, 2, 3]
        assert truncated is False

    def test_limit_less_than_length(self) -> None:
        items = [1, 2, 3, 4, 5]
        result, truncated = apply_limit(items, 2)
        assert result == [1, 2]
        assert truncated is True

    def test_limit_of_one(self) -> None:
        items = [1, 2, 3]
        result, truncated = apply_limit(items, 1)
        assert result == [1]
        assert truncated is True

    def test_limit_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="greater than or equal to 1"):
            apply_limit([1, 2], 0)

    def test_negative_limit_raises(self) -> None:
        with pytest.raises(ValueError, match="greater than or equal to 1"):
            apply_limit([1, 2], -1)

    def test_empty_list_with_limit(self) -> None:
        result, truncated = apply_limit([], 5)
        assert result == []
        assert truncated is False


# --- location_key ---


class TestLocationKey:
    """Tests for the shared location_key helper."""

    def test_produces_stable_tuple(self) -> None:
        loc = Location(
            file_path="/tmp/foo.py",
            range=Range(
                start=Position(line=10, character=5),
                end=Position(line=10, character=15),
            ),
        )
        key = location_key(loc)
        assert key == ("/tmp/foo.py", 10, 5, 10, 15)

    def test_identical_locations_same_key(self) -> None:
        loc1 = Location(
            file_path="/tmp/a.py",
            range=Range(start=Position(line=1, character=0), end=Position(line=1, character=5)),
        )
        loc2 = Location(
            file_path="/tmp/a.py",
            range=Range(start=Position(line=1, character=0), end=Position(line=1, character=5)),
        )
        assert location_key(loc1) == location_key(loc2)


# --- diagnostic_key ---


class TestDiagnosticKey:
    """Tests for the shared diagnostic_key helper."""

    def test_produces_stable_tuple(self) -> None:
        diag = Diagnostic(
            file_path="/tmp/foo.py",
            range=Range(start=Position(line=5, character=0), end=Position(line=5, character=10)),
            severity="error",
            message="something wrong",
        )
        key = diagnostic_key(diag)
        assert key == ("/tmp/foo.py", 5, 0, 5, 10, "error", "something wrong")


# --- python_files ---


class TestPythonFiles:
    """Tests for the filtered python_files utility."""

    def test_finds_python_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("# a")
        (tmp_path / "b.py").write_text("# b")
        (tmp_path / "c.txt").write_text("not python")
        result = python_files(tmp_path)
        names = [p.name for p in result]
        assert "a.py" in names
        assert "b.py" in names
        assert "c.txt" not in names

    def test_excludes_venv(self, tmp_path: Path) -> None:
        venv_dir = tmp_path / ".venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "module.py").write_text("# venv")
        (tmp_path / "real.py").write_text("# real")
        result = python_files(tmp_path)
        names = [p.name for p in result]
        assert "real.py" in names
        assert "module.py" not in names

    def test_excludes_pycache(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "cached.py").write_text("# cache")
        (tmp_path / "main.py").write_text("# main")
        result = python_files(tmp_path)
        names = [p.name for p in result]
        assert "main.py" in names
        assert "cached.py" not in names

    def test_excludes_git(self, tmp_path: Path) -> None:
        git_dir = tmp_path / ".git" / "hooks"
        git_dir.mkdir(parents=True)
        (git_dir / "pre-commit.py").write_text("# hook")
        (tmp_path / "src.py").write_text("# src")
        result = python_files(tmp_path)
        names = [p.name for p in result]
        assert "src.py" in names
        assert "pre-commit.py" not in names

    def test_custom_excludes(self, tmp_path: Path) -> None:
        custom_dir = tmp_path / "vendor"
        custom_dir.mkdir()
        (custom_dir / "lib.py").write_text("# vendored")
        (tmp_path / "app.py").write_text("# app")
        result = python_files(tmp_path, exclude_dirs={"vendor"})
        names = [p.name for p in result]
        assert "app.py" in names
        assert "lib.py" not in names

    def test_results_are_sorted(self, tmp_path: Path) -> None:
        (tmp_path / "z.py").write_text("")
        (tmp_path / "a.py").write_text("")
        (tmp_path / "m.py").write_text("")
        result = python_files(tmp_path)
        names = [p.name for p in result]
        assert names == sorted(names)


# --- normalize_path / path_to_uri / uri_to_path ---


class TestPathConversions:
    """Tests for canonical path and URI conversion helpers."""

    def test_normalize_path_returns_absolute(self) -> None:
        result = normalize_path("relative/path.py")
        assert os.path.isabs(result)

    def test_path_to_uri_starts_with_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.py"
        test_file.write_text("")
        uri = path_to_uri(str(test_file))
        assert uri.startswith("file:///")

    def test_uri_round_trip(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.py"
        test_file.write_text("")
        original = normalize_path(str(test_file))
        uri = path_to_uri(original)
        restored = uri_to_path(uri)
        assert restored == original

    def test_uri_to_path_rejects_non_file_scheme(self) -> None:
        with pytest.raises(ValueError, match="Unsupported URI scheme"):
            uri_to_path("https://example.com/path")
