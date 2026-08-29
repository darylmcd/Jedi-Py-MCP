"""Regression coverage for changelog fragment validation and PR coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.changelog_fragments import (
    load_fragments,
    render_release_body,
    validate_change_coverage,
)


def _fragment_dir(tmp_path: Path) -> Path:
    fragment_dir = tmp_path / "changelog.d"
    fragment_dir.mkdir()
    (fragment_dir / "README.md").write_text("schema\n", encoding="utf-8")
    return fragment_dir


@pytest.mark.parametrize(
    ("filename", "body", "message"),
    [
        ("Fixed-bad.md", "- **Fixed:** Text.\n", "filename"),
        ("fixed-bad.txt", "- **Fixed:** Text.\n", "filename"),
        ("unknown-bad.md", "- **Fixed:** Text.\n", "filename"),
        ("fixed-bad.md", "- **Added:** Text.\n", "must start"),
        ("fixed-bad.md", "- **Fixed:** One.\n- **Fixed:** Two.\n", "exactly one"),
    ],
)
def test_load_fragments_rejects_malformed_fragment(
    tmp_path: Path,
    filename: str,
    body: str,
    message: str,
) -> None:
    fragment_dir = _fragment_dir(tmp_path)
    (fragment_dir / filename).write_text(body, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_fragments(fragment_dir)


def test_render_release_body_uses_canonical_category_order(tmp_path: Path) -> None:
    fragment_dir = _fragment_dir(tmp_path)
    (fragment_dir / "maintenance-tooling.md").write_text(
        "- **Maintenance:** Tooling.\n", encoding="utf-8"
    )
    (fragment_dir / "fixed-defect.md").write_text("- **Fixed:** Defect.\n", encoding="utf-8")

    body = render_release_body(load_fragments(fragment_dir))

    assert body.index("### Fixed") < body.index("### Maintenance")


def test_material_change_requires_changed_valid_fragment() -> None:
    with pytest.raises(ValueError, match="require a changed"):
        validate_change_coverage(["src/package.py", "ai_docs/backlog.md"], set())


def test_planning_only_change_does_not_require_fragment() -> None:
    validate_change_coverage(["ai_docs/backlog.md", "ai_docs/items/work.md"], set())


def test_material_change_accepts_changed_valid_fragment() -> None:
    validate_change_coverage(
        ["tests/unit/test_feature.py", "changelog.d/fixed-feature.md"],
        {"changelog.d/fixed-feature.md"},
    )
