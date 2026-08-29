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
        f"## [{version}] - 2026-01-01\n\n"
        "### Added\n\n"
        "- **Added:** Initial release.\n\n"
        f"[Unreleased]: https://github.com/darylmcd/Jedi-Py-MCP/compare/v{version}...HEAD\n"
        f"[{version}]: https://github.com/darylmcd/Jedi-Py-MCP/releases/tag/v{version}\n",
        encoding="utf-8",
    )
    fragment_dir = tmp_path / "changelog.d"
    fragment_dir.mkdir()
    (fragment_dir / "fixed-regression.md").write_text(
        "- **Fixed:** Corrected a regression.\n", encoding="utf-8"
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
    assemble_changelog(
        files.changelog,
        files.changelog_fragments,
        current,
        target,
        date(2026, 8, 28),
    )

    assert read_release_version(files) == target
    changelog = files.changelog.read_text(encoding="utf-8")
    assert "## [Unreleased]\n\n## [1.2.4] - 2026-08-28" in changelog
    assert "### Fixed\n\n- **Fixed:** Corrected a regression." in changelog
    assert "compare/v1.2.4...HEAD" in changelog
    assert "[1.2.4]: https://github.com/darylmcd/Jedi-Py-MCP/releases/tag/v1.2.4" in changelog
    assert list(files.changelog_fragments.glob("*.md")) == []


def test_assemble_changelog_refuses_populated_unreleased_section(tmp_path: Path) -> None:
    files = _release_files(tmp_path)
    files.changelog.write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Fixed\n\n- **Fixed:** Competing direct note.\n\n"
        "## [1.2.3] - 2026-01-01\n\n"
        "[Unreleased]: https://github.com/darylmcd/Jedi-Py-MCP/compare/v1.2.3...HEAD\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unreleased must stay empty"):
        assemble_changelog(
            files.changelog,
            files.changelog_fragments,
            ReleaseVersion.parse("1.2.3"),
            ReleaseVersion.parse("1.2.4"),
            date.today(),
        )


def test_assemble_changelog_orders_categories_and_filenames(tmp_path: Path) -> None:
    files = _release_files(tmp_path)
    (files.changelog_fragments / "added-feature.md").write_text(
        "- **Added:** Added a feature.\n", encoding="utf-8"
    )
    (files.changelog_fragments / "fixed-another.md").write_text(
        "- **Fixed:** Corrected another regression.\n", encoding="utf-8"
    )

    assemble_changelog(
        files.changelog,
        files.changelog_fragments,
        ReleaseVersion.parse("1.2.3"),
        ReleaseVersion.parse("1.2.4"),
        date.today(),
    )

    changelog = files.changelog.read_text(encoding="utf-8")
    assert changelog.index("Corrected another") < changelog.index("Corrected a regression")
    assert changelog.index("### Fixed") < changelog.index("### Added")


def test_assemble_changelog_restores_fragments_when_consumption_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _release_files(tmp_path)
    second = files.changelog_fragments / "maintenance-release.md"
    second.write_text("- **Maintenance:** Updated release tooling.\n", encoding="utf-8")
    original_changelog = files.changelog.read_bytes()
    original_fragments = {path: path.read_bytes() for path in files.changelog_fragments.glob("*.md")}
    deleted = 0
    real_delete = bump_reinstall._delete_fragment

    def _fail_second_delete(path: Path) -> None:
        nonlocal deleted
        deleted += 1
        if deleted == 2:
            raise OSError("delete failed")
        real_delete(path)

    monkeypatch.setattr(bump_reinstall, "_delete_fragment", _fail_second_delete)

    with pytest.raises(OSError, match="delete failed"):
        assemble_changelog(
            files.changelog,
            files.changelog_fragments,
            ReleaseVersion.parse("1.2.3"),
            ReleaseVersion.parse("1.2.4"),
            date.today(),
        )

    assert files.changelog.read_bytes() == original_changelog
    assert {path: path.read_bytes() for path in files.changelog_fragments.glob("*.md")} == original_fragments


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
    assert any(command[-3:] == ["-m", "pip", "check"] for command in calls)
    assert list(files.changelog_fragments.glob("*.md")) == []


def test_bump_and_reinstall_restores_release_files_when_a_command_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _release_files(tmp_path)
    originals = {path: path.read_bytes() for path in files.all()}
    original_fragments = {path: path.read_bytes() for path in files.changelog_fragments.glob("*.md")}

    monkeypatch.setattr(bump_reinstall, "_resolve_executable", lambda raw: raw)

    def fail_lock(arguments: list[str], repo_root: Path) -> str:
        raise RuntimeError("lock failed")

    monkeypatch.setattr(bump_reinstall, "_run", fail_lock)

    with pytest.raises(RuntimeError, match="lock failed"):
        bump_reinstall.bump_and_reinstall(tmp_path, "patch", "python")

    assert {path: path.read_bytes() for path in files.all()} == originals
    assert {path: path.read_bytes() for path in files.changelog_fragments.glob("*.md")} == original_fragments


def test_bump_and_reinstall_retains_release_files_after_installation_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = _release_files(tmp_path)

    monkeypatch.setattr(bump_reinstall, "_resolve_executable", lambda raw: raw)

    def fail_install(arguments: list[str], repo_root: Path) -> str:
        if "install" in arguments:
            raise RuntimeError("install failed")
        return ""

    monkeypatch.setattr(bump_reinstall, "_run", fail_install)

    with pytest.raises(RuntimeError, match="release files were finalized"):
        bump_reinstall.bump_and_reinstall(tmp_path, "patch", "python")

    assert read_release_version(files) == ReleaseVersion.parse("1.2.4")
    assert "## [1.2.4]" in files.changelog.read_text(encoding="utf-8")


def test_reinstall_current_does_not_mutate_release_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    files = _release_files(tmp_path)
    originals = {path: path.read_bytes() for path in files.all()}
    calls: list[list[str]] = []

    monkeypatch.setattr(bump_reinstall, "_resolve_executable", lambda raw: raw)

    def fake_run(arguments: list[str], repo_root: Path) -> str:
        calls.append(arguments)
        if arguments[-2:] == ["python_refactor_mcp", "--version"]:
            return "python-refactor-mcp 1.2.3"
        return ""

    monkeypatch.setattr(bump_reinstall, "_run", fake_run)

    assert bump_reinstall.reinstall_current(tmp_path, "python") == ReleaseVersion.parse("1.2.3")
    assert {path: path.read_bytes() for path in files.all()} == originals
    assert ["uv", "lock", "--check"] in calls
    assert any(command[-3:] == ["-m", "pip", "check"] for command in calls)
