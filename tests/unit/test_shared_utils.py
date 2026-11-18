"""Unit tests for consolidated shared utilities."""

from __future__ import annotations

import ntpath
import os
import posixpath
from pathlib import Path
from unittest.mock import patch

import pytest

from python_refactor_mcp.errors import ToolInputError
from python_refactor_mcp.models import Diagnostic, Location, Position, Range
from python_refactor_mcp.util.file_filter import python_files
from python_refactor_mcp.util.paths import normalize_path, path_to_uri, uri_to_path
from python_refactor_mcp.util.shared import (
    apply_limit,
    diagnostic_key,
    is_network_or_device_path,
    location_key,
    require_local_path,
    resolve_workspace_dir,
    validate_workspace_path,
)

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


# --- resolve_workspace_dir ---


class TestResolveWorkspaceDir:
    """Tests for workspace-relative-or-absolute directory resolution."""

    def test_relative_value_anchors_at_workspace_root(self, tmp_path: Path) -> None:
        result = resolve_workspace_dir("typings/sub", tmp_path)
        assert result == str((tmp_path / "typings" / "sub").resolve())

    def test_absolute_value_inside_workspace_is_kept(self, tmp_path: Path) -> None:
        target = tmp_path / "stubs"
        assert resolve_workspace_dir(str(target), tmp_path) == str(target.resolve())

    def test_relative_escape_is_rejected(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        with pytest.raises(ToolInputError, match="outside the workspace root"):
            resolve_workspace_dir("../outside", workspace)

    def test_absolute_path_outside_workspace_is_rejected(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        with pytest.raises(ToolInputError, match="outside the workspace root"):
            resolve_workspace_dir(str(tmp_path / "elsewhere"), workspace)


# --- is_network_or_device_path / require_local_path ---

_UNC_OR_DEVICE_SPELLINGS = [
    r"\\srv\share\a.py",
    "//srv/share/a.py",
    r"\/srv\share\a.py",
    r"\\?\UNC\srv\s\a.py",
    "//?/UNC/srv/share/a.py",
    r"\\?\Volume{01234567-89ab-cdef-0123-456789abcdef}\a.py",
    r"\\?\GLOBALROOT\Device\x",
    r"\\?\C::\a.py",
    r"\\.\pipe\x",
    r"\\.\C:\a.py",
]
_LOCAL_SPELLINGS = [
    r"C:\work\a.py",
    "C:/work/a.py",
    r"\\?\C:\work\a.py",
    r"\\?\c:\work\a.py",
    r"\\?\C:",
    r"\work\a.py",
    r"rel\a.py",
    "a.py",
]


class TestNetworkOrDevicePath:
    """UNC and device-namespace classification is pure string work, so it runs on any OS through ``pathmod``."""

    @pytest.mark.parametrize("value", _UNC_OR_DEVICE_SPELLINGS)
    def test_unc_and_device_spellings_are_rejected(self, value: str) -> None:
        assert is_network_or_device_path(value, pathmod=ntpath)
        with pytest.raises(ToolInputError, match="UNC or device-namespace path"):
            require_local_path(value, "parameter: file_path", pathmod=ntpath)

    @pytest.mark.parametrize("value", _LOCAL_SPELLINGS)
    def test_local_spellings_are_allowed(self, value: str) -> None:
        assert not is_network_or_device_path(value, pathmod=ntpath)
        require_local_path(value, "parameter: file_path", pathmod=ntpath)

    @pytest.mark.parametrize("value", ["//srv/share/a.py", r"\\srv\share\a.py", "/work/a.py"])
    def test_posix_rules_never_classify_a_path_as_unc(self, value: str) -> None:
        assert not is_network_or_device_path(value, pathmod=posixpath)

    def test_the_message_names_the_value_and_where(self) -> None:
        with pytest.raises(ToolInputError, match=r"'\\\\srv\\share' .*\(parameter: root_path\)"):
            require_local_path(r"\\srv\share", "parameter: root_path", pathmod=ntpath)


@pytest.mark.skipif(os.name != "nt", reason="UNC paths exist only on Windows")
class TestUncRejectedBeforeFilesystemAccess:
    """On Windows the host rules apply, so the shared helpers reject before ``Path.resolve()``."""

    @pytest.mark.parametrize("value", [r"\\unc-srv\share\a.py", r"\\?\UNC\unc-srv\share\a.py", r"\\.\pipe\unc-srv"])
    def test_validate_workspace_path(self, tmp_path: Path, value: str) -> None:
        with (
            patch.object(Path, "resolve", side_effect=AssertionError("resolve reached")),
            pytest.raises(ToolInputError, match="UNC or device-namespace path"),
        ):
            validate_workspace_path(value, tmp_path)

    def test_resolve_workspace_dir(self, tmp_path: Path) -> None:
        with (
            patch.object(Path, "resolve", side_effect=AssertionError("resolve reached")),
            pytest.raises(ToolInputError, match="UNC or device-namespace path"),
        ):
            resolve_workspace_dir(r"\\unc-srv\share\out", tmp_path)
