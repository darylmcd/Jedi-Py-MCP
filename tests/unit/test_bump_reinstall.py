"""Regression coverage for the guarded bump-and-reinstall release helper."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts import bump_reinstall
from scripts.bump_reinstall import (
    ReleaseFiles,
    ReleaseVersion,
    assemble_changelog,
    read_release_version,
    resolve_target,
    update_version_surfaces,
)


def _release_files(tmp_path: Path, version: str = "1.2.3") -> ReleaseFiles:
    package_dir = tmp_path / "src" / "python_refactor_mcp"
    package_dir.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "python-refactor-mcp"\nversion = "{version}"\n', encoding="utf-8"
    )
    (package_dir / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"manifest_version": "0.3", "version": version}, indent=2) + "\n", encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Fixed\n\n"
        "- **Fixed:** Corrected a regression.\n\n"
        f"## [{version}] - 2026-01-01\n\n"
        "### Added\n\n"
        "- **Added:** Initial release.\n\n"
        f"[Unreleased]: https://github.com/darylmcd/Jedi-Py-MCP/compare/v{version}...HEAD\n"
        f"[{version}]: https://github.com/darylmcd/Jedi-Py-MCP/releases/tag/v{version}\n",
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    return ReleaseFiles.from_root(tmp_path)


@pytest.mark.parametrize(
    ("requested", "expected"),
    [("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0"), ("3.4.5", "3.4.5")],
)
def test_resolve_target_accepts_bump_kinds_and_greater_explicit_versions(requested: str, expected: str) -> None:
    assert str(resolve_target(ReleaseVersion.parse("1.2.3"), requested)) == expected


@pytest.mark.parametrize("requested", ["1.2.3", "1.2.2", "v1.2.4", "1.2", "01.2.4"])
def test_resolve_target_rejects_non_increasing_or_non_release_versions(requested: str) -> None:
    with pytest.raises(ValueError):
        resolve_target(ReleaseVersion.parse("1.2.3"), requested)


def test_read_release_version_rejects_drift(tmp_path: Path) -> None:
    files = _release_files(tmp_path)
    files.manifest.write_text('{"version": "1.2.4"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="surfaces disagree"):
        read_release_version(files)


def test_update_surfaces_and_assemble_changelog(tmp_path: Path) -> None:
    files = _release_files(tmp_path)
    current = read_release_version(files)
    target = ReleaseVersion.parse("1.2.4")

    update_version_surfaces(files, current, target)
    assemble_changelog(files.changelog, current, target, date(2026, 8, 28))

    assert read_release_version(files) == target
    changelog = files.changelog.read_text(encoding="utf-8")
    assert "## [Unreleased]\n\n## [1.2.4] - 2026-08-28" in changelog
    assert "### Fixed\n\n- **Fixed:** Corrected a regression." in changelog
    assert "compare/v1.2.4...HEAD" in changelog
    assert "[1.2.4]: https://github.com/darylmcd/Jedi-Py-MCP/releases/tag/v1.2.4" in changelog


def test_assemble_changelog_refuses_empty_unreleased_section(tmp_path: Path) -> None:
    files = _release_files(tmp_path)
    files.changelog.write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "## [1.2.3] - 2026-01-01\n\n"
        "[Unreleased]: https://github.com/darylmcd/Jedi-Py-MCP/compare/v1.2.3...HEAD\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="empty Unreleased"):
        assemble_changelog(files.changelog, ReleaseVersion.parse("1.2.3"), ReleaseVersion.parse("1.2.4"), date.today())


def test_bump_and_reinstall_orchestrates_locked_install_and_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _release_files(tmp_path)
    calls: list[list[str]] = []

    monkeypatch.setattr(bump_reinstall, "_resolve_executable", lambda raw: raw)

    def fake_run(arguments: list[str], repo_root: Path) -> str:
        assert repo_root == tmp_path
        calls.append(arguments)
        if arguments[-2:] == ["python_refactor_mcp", "--version"]:
            return "python-refactor-mcp 1.2.4"
        return ""

    monkeypatch.setattr(bump_reinstall, "_run", fake_run)

    assert bump_reinstall.bump_and_reinstall(tmp_path, "patch", "python") == ReleaseVersion.parse("1.2.4")
    assert read_release_version(files) == ReleaseVersion.parse("1.2.4")
    assert ["uv", "lock"] in calls
    assert any("--no-emit-project" in command for command in calls)
    assert any("--force-reinstall" in command and "--no-deps" in command for command in calls)


def test_bump_and_reinstall_restores_release_files_when_a_command_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _release_files(tmp_path)
    originals = {path: path.read_bytes() for path in files.all()}

    monkeypatch.setattr(bump_reinstall, "_resolve_executable", lambda raw: raw)

    def fail_lock(arguments: list[str], repo_root: Path) -> str:
        raise RuntimeError("lock failed")

    monkeypatch.setattr(bump_reinstall, "_run", fail_lock)

    with pytest.raises(RuntimeError, match="lock failed"):
        bump_reinstall.bump_and_reinstall(tmp_path, "patch", "python")

    assert {path: path.read_bytes() for path in files.all()} == originals
