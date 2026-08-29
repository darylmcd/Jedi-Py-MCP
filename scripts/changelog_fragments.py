"""Validate changelog fragments and enforce change-bearing PR coverage."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final


@dataclass(frozen=True)
class Category:
    """One canonical changelog category."""

    slug: str
    heading: str
    prefix: str


CATEGORIES: Final = (
    Category("fixed", "Fixed", "Fixed"),
    Category("changed-breaking", "Changed — BREAKING", "Changed — BREAKING"),
    Category("changed", "Changed", "Changed"),
    Category("added", "Added", "Added"),
    Category("maintenance", "Maintenance", "Maintenance"),
)
_CATEGORY_BY_SLUG: Final = {category.slug: category for category in CATEGORIES}
_CATEGORY_ORDER: Final = {category.slug: index for index, category in enumerate(CATEGORIES)}
_FILENAME_RE: Final = re.compile(
    r"^(fixed|changed-breaking|changed|added|maintenance)-[a-z0-9]+(?:-[a-z0-9]+)*\.md$"
)
_ROOT_FILES_REQUIRING_FRAGMENT: Final = frozenset(
    {
        "README.md",
        "build.bat",
        "justfile",
        "manifest.json",
        "pyproject.toml",
        "python-refactor-mcp.spec",
        "uv.lock",
    }
)
_PREFIXES_REQUIRING_FRAGMENT: Final = (
    "src/",
    "tests/",
    "scripts/",
    "docs/",
    ".github/workflows/",
)


@dataclass(frozen=True)
class ChangelogFragment:
    """One validated changelog fragment."""

    path: Path
    category: Category
    bullet: str


def load_fragments(fragment_dir: Path) -> list[ChangelogFragment]:
    """Load every fragment after strict filename and one-bullet validation."""
    if not fragment_dir.is_dir():
        raise ValueError(f"Missing changelog fragment directory: {fragment_dir}")

    fragments: list[ChangelogFragment] = []
    for path in sorted(candidate for candidate in fragment_dir.iterdir() if candidate.is_file()):
        if path.name == "README.md":
            continue
        match = _FILENAME_RE.fullmatch(path.name)
        if match is None:
            raise ValueError(
                f"Invalid changelog fragment filename {path.name!r}; expected "
                "<category>-<lowercase-kebab-slug>.md"
            )
        category = _CATEGORY_BY_SLUG[match.group(1)]
        nonblank = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(nonblank) != 1:
            raise ValueError(f"{path.name} must contain exactly one nonblank bullet line")
        expected_prefix = f"- **{category.prefix}:** "
        bullet = nonblank[0]
        if not bullet.startswith(expected_prefix) or bullet == expected_prefix:
            raise ValueError(f"{path.name} must start with {expected_prefix!r} and include text")
        fragments.append(ChangelogFragment(path=path, category=category, bullet=bullet))

    return sorted(fragments, key=lambda item: (_CATEGORY_ORDER[item.category.slug], item.path.name))


def render_release_body(fragments: list[ChangelogFragment]) -> str:
    """Group validated fragments in canonical category and filename order."""
    sections: list[str] = []
    for category in CATEGORIES:
        bullets = [fragment.bullet for fragment in fragments if fragment.category == category]
        if bullets:
            sections.append(f"### {category.heading}\n\n" + "\n".join(bullets))
    return "\n\n".join(sections)


def change_requires_fragment(path: str) -> bool:
    """Return whether a repository-relative change needs release-note coverage."""
    normalized = path.replace("\\", "/")
    return normalized in _ROOT_FILES_REQUIRING_FRAGMENT or normalized.startswith(
        _PREFIXES_REQUIRING_FRAGMENT
    )


def validate_change_coverage(changed_paths: list[str], valid_fragment_paths: set[str]) -> None:
    """Require at least one changed, currently valid fragment for material changes."""
    material = sorted(path for path in changed_paths if change_requires_fragment(path))
    changed_fragments = {
        path.replace("\\", "/")
        for path in changed_paths
        if path.replace("\\", "/").startswith("changelog.d/")
        and path.replace("\\", "/") != "changelog.d/README.md"
    }
    if material and not (changed_fragments & valid_fragment_paths):
        sample = ", ".join(material[:5])
        raise ValueError(f"Material changes require a changed, valid changelog fragment; found: {sample}")


def _git_changed_paths(repo_root: Path, base_ref: str) -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRT", f"{base_ref}...HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]


def validate_repository(repo_root: Path, base_ref: str | None = None) -> list[ChangelogFragment]:
    """Validate all fragments and optional PR-diff coverage."""
    fragment_dir = repo_root / "changelog.d"
    fragments = load_fragments(fragment_dir)
    if base_ref:
        valid_paths = {fragment.path.relative_to(repo_root).as_posix() for fragment in fragments}
        validate_change_coverage(_git_changed_paths(repo_root, base_ref), valid_paths)
    return fragments


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-ref",
        default=os.getenv("CHANGELOG_BASE_REF") or None,
        help="optional base commit/ref used to require a changed fragment",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    try:
        fragments = validate_repository(repo_root, args.base_ref)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"changelog fragment validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Validated {len(fragments)} changelog fragment(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
