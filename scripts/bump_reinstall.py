"""Atomically bump release metadata, refresh the lock, and reinstall the server."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

_PACKAGE_NAME: Final = "python-refactor-mcp"
_VERSION_PATTERN: Final = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_BUMP_KINDS: Final = frozenset({"major", "minor", "patch"})


@dataclass(frozen=True, order=True)
class ReleaseVersion:
    """A stable SemVer release without prerelease or build metadata."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, raw: str) -> ReleaseVersion:
        """Parse the repository's supported ``major.minor.patch`` form."""
        match = _VERSION_PATTERN.fullmatch(raw)
        if match is None:
            raise ValueError(f"Invalid release version {raw!r}; expected major.minor.patch")
        return cls(*(int(part) for part in match.groups()))

    def bump(self, kind: str) -> ReleaseVersion:
        """Return the next release for *kind*."""
        if kind == "major":
            return ReleaseVersion(self.major + 1, 0, 0)
        if kind == "minor":
            return ReleaseVersion(self.major, self.minor + 1, 0)
        if kind == "patch":
            return ReleaseVersion(self.major, self.minor, self.patch + 1)
        raise ValueError(f"Unknown bump kind {kind!r}; expected major, minor, or patch")

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ReleaseFiles:
    """Release-managed files rooted at one checkout."""

    pyproject: Path
    package_init: Path
    manifest: Path
    changelog: Path
    lock: Path

    @classmethod
    def from_root(cls, repo_root: Path) -> ReleaseFiles:
        return cls(
            pyproject=repo_root / "pyproject.toml",
            package_init=repo_root / "src" / "python_refactor_mcp" / "__init__.py",
            manifest=repo_root / "manifest.json",
            changelog=repo_root / "CHANGELOG.md",
            lock=repo_root / "uv.lock",
        )

    def all(self) -> tuple[Path, ...]:
        return (self.pyproject, self.package_init, self.manifest, self.changelog, self.lock)


def read_release_version(files: ReleaseFiles) -> ReleaseVersion:
    """Read and cross-check every hand-maintained version surface."""
    pyproject = tomllib.loads(files.pyproject.read_text(encoding="utf-8"))
    manifest = json.loads(files.manifest.read_text(encoding="utf-8"))
    init_text = files.package_init.read_text(encoding="utf-8")
    init_matches = re.findall(r'(?m)^__version__\s*=\s*"([^"]+)"\s*$', init_text)
    if len(init_matches) != 1:
        raise ValueError(f"Expected one __version__ assignment in {files.package_init}")

    raw_versions = {
        "pyproject.toml": pyproject["project"]["version"],
        "package __version__": init_matches[0],
        "manifest.json": manifest["version"],
    }
    if len(set(raw_versions.values())) != 1:
        details = ", ".join(f"{name}={value}" for name, value in raw_versions.items())
        raise ValueError(f"Release version surfaces disagree: {details}")
    return ReleaseVersion.parse(next(iter(raw_versions.values())))


def resolve_target(current: ReleaseVersion, requested: str) -> ReleaseVersion:
    """Resolve a bump kind or explicit version and require forward progress."""
    target = current.bump(requested) if requested in _BUMP_KINDS else ReleaseVersion.parse(requested)
    if target <= current:
        raise ValueError(f"Target version {target} must be greater than current version {current}")
    return target


def _replace_exactly_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"Expected exactly one {label}; found {count}")
    return updated


def update_version_surfaces(files: ReleaseFiles, current: ReleaseVersion, target: ReleaseVersion) -> None:
    """Update the three hand-maintained version files."""
    old = re.escape(str(current))
    new = str(target)
    replacements = {
        files.pyproject: (rf'^(version\s*=\s*)"{old}"\s*$', rf'\g<1>"{new}"', "project version"),
        files.package_init: (rf'^(__version__\s*=\s*)"{old}"\s*$', rf'\g<1>"{new}"', "package version"),
        files.manifest: (rf'^(\s*"version"\s*:\s*)"{old}"(\s*,?\s*)$', rf'\g<1>"{new}"\g<2>', "manifest version"),
    }
    for path, (pattern, replacement, label) in replacements.items():
        original = path.read_text(encoding="utf-8")
        _atomic_write_text(path, _replace_exactly_once(original, pattern, replacement, label))


def assemble_changelog(changelog: Path, current: ReleaseVersion, target: ReleaseVersion, released_on: date) -> None:
    """Move the populated Unreleased body into a dated release section."""
    original = changelog.read_text(encoding="utf-8")
    normalized = original.replace("\r\n", "\n")
    section_match = re.search(r"(?ms)^## \[Unreleased\]\s*\n(?P<body>.*?)(?=^## \[)", normalized)
    if section_match is None:
        raise ValueError("CHANGELOG.md must contain an Unreleased section followed by a released section")
    body = section_match.group("body").strip()
    if not body:
        raise ValueError("Refusing to cut a release from an empty Unreleased section")

    release_section = f"## [Unreleased]\n\n## [{target}] - {released_on.isoformat()}\n\n{body}\n\n"
    updated = normalized[: section_match.start()] + release_section + normalized[section_match.end() :]
    updated = _replace_exactly_once(
        updated,
        rf"^\[Unreleased\]: .*/compare/v{re.escape(str(current))}\.\.\.HEAD$",
        f"[Unreleased]: https://github.com/darylmcd/Jedi-Py-MCP/compare/v{target}...HEAD",
        "Unreleased comparison link",
    )
    link = f"[{target}]: https://github.com/darylmcd/Jedi-Py-MCP/releases/tag/v{target}"
    updated = _replace_exactly_once(
        updated,
        r"^(\[Unreleased\]:[^\n]+)$",
        rf"\g<1>\n{link}",
        "Unreleased link anchor",
    )
    newline = "\r\n" if "\r\n" in original else "\n"
    _atomic_write_text(changelog, updated.replace("\n", newline), newline="")


def _atomic_write_text(path: Path, content: str, *, newline: str | None = None) -> None:
    """Replace a UTF-8 text file without exposing a partially-written version."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline=newline,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    try:
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _run(arguments: list[str], repo_root: Path) -> str:
    """Run a release command and return its captured standard output."""
    display = subprocess.list2cmdline(arguments)
    print(f"> {display}", flush=True)
    completed = subprocess.run(arguments, cwd=repo_root, check=True, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    return completed.stdout.strip()


def _resolve_executable(raw: str) -> str:
    candidate = Path(raw)
    if candidate.is_file():
        return str(candidate.resolve())
    resolved = shutil.which(raw)
    if resolved is None:
        raise FileNotFoundError(f"Executable not found: {raw}")
    return resolved


def _export_locked_runtime(uv_executable: str, repo_root: Path, requirements: Path) -> None:
    """Export exact runtime dependencies from the committed lock."""
    _run(
        [
            uv_executable,
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--output-file",
            str(requirements),
        ],
        repo_root,
    )


def _install_and_verify(repo_root: Path, python_executable: str, requirements: Path, expected: ReleaseVersion) -> None:
    """Synchronize one interpreter, validate its dependency graph, and probe the CLI."""
    _run([python_executable, "-m", "pip", "install", "--upgrade", "-r", str(requirements)], repo_root)
    _run(
        [python_executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", "--editable", "."],
        repo_root,
    )
    _run([python_executable, "-m", "pip", "check"], repo_root)
    reported = _run([python_executable, "-m", "python_refactor_mcp", "--version"], repo_root)
    expected_output = f"{_PACKAGE_NAME} {expected}"
    if reported != expected_output:
        raise RuntimeError(f"Reinstalled CLI reported {reported!r}; expected {expected_output!r}")


def reinstall_current(repo_root: Path, target_python: str) -> ReleaseVersion:
    """Repair or refresh the current release without mutating release metadata."""
    files = ReleaseFiles.from_root(repo_root)
    missing = [str(path) for path in files.all() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing release-managed files: {', '.join(missing)}")

    current = read_release_version(files)
    python_executable = _resolve_executable(target_python)
    uv_executable = _resolve_executable("uv")
    _run([uv_executable, "lock", "--check"], repo_root)
    with tempfile.TemporaryDirectory(prefix="python-refactor-mcp-reinstall-") as temp_dir:
        requirements = Path(temp_dir) / "runtime-requirements.txt"
        _export_locked_runtime(uv_executable, repo_root, requirements)
        _install_and_verify(repo_root, python_executable, requirements, current)
    print(f"Reinstalled {_PACKAGE_NAME} {current} and verified {python_executable}.")
    return current


def bump_and_reinstall(repo_root: Path, requested: str, target_python: str) -> ReleaseVersion:
    """Execute the guarded bump, lock refresh, locked reinstall, and CLI verification."""
    files = ReleaseFiles.from_root(repo_root)
    missing = [str(path) for path in files.all() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing release-managed files: {', '.join(missing)}")

    current = read_release_version(files)
    target = resolve_target(current, requested)
    python_executable = _resolve_executable(target_python)
    uv_executable = _resolve_executable("uv")
    snapshots = {path: path.read_bytes() for path in files.all()}

    with tempfile.TemporaryDirectory(prefix="python-refactor-mcp-release-") as temp_dir:
        requirements = Path(temp_dir) / "runtime-requirements.txt"
        try:
            update_version_surfaces(files, current, target)
            assemble_changelog(files.changelog, current, target, date.today())
            _run([uv_executable, "lock"], repo_root)
            _export_locked_runtime(uv_executable, repo_root, requirements)
        except BaseException:
            for path, content in snapshots.items():
                path.write_bytes(content)
            raise

        try:
            _install_and_verify(repo_root, python_executable, requirements, target)
        except BaseException as exc:
            raise RuntimeError(
                "Installation failed after release files were finalized; they were retained to match any partial "
                f"environment changes. Repair with: just reinstall {target_python!r}"
            ) from exc

    if read_release_version(files) != target:
        raise RuntimeError("Release version surfaces drifted during the bump")

    print(f"Bumped {_PACKAGE_NAME} {current} -> {target} and verified {python_executable}.")
    return target


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "version",
        nargs="?",
        help="major, minor, patch, or an explicit greater major.minor.patch version",
    )
    parser.add_argument(
        "--reinstall-only",
        action="store_true",
        help="reinstall and verify the current locked release without changing version metadata",
    )
    parser.add_argument(
        "--target-python",
        default="python",
        help="Python executable to reinstall into (default: python on PATH, matching manifest.json)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    try:
        if args.reinstall_only:
            if args.version is not None:
                raise ValueError("--reinstall-only does not accept a version")
            reinstall_current(repo_root, args.target_python)
        else:
            if args.version is None:
                raise ValueError("a bump version or --reinstall-only is required")
            bump_and_reinstall(repo_root, args.version, args.target_python)
    except (FileNotFoundError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"bump-reinstall failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
