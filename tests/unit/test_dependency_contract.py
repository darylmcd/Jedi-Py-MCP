"""Regression coverage for install and CI dependency compatibility."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_mcp_dependency_targets_current_major_version() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    mcp_requirement = next(
        Requirement(raw)
        for raw in pyproject["project"]["dependencies"]
        if Requirement(raw).name == "mcp"
    )

    assert mcp_requirement.specifier.contains("2.1")
    assert not mcp_requirement.specifier.contains("3.0")


def test_hosted_ci_syncs_the_authoritative_lockfile() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "uv sync --locked --all-extras" in workflow
    assert 'pip install -e ".[dev,build]"' not in workflow


def test_hosted_ci_actions_are_pinned_to_commits() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    action_refs = [
        line.partition("uses:")[2].strip().split(maxsplit=1)[0]
        for line in workflow.splitlines()
        if "uses:" in line
    ]

    assert action_refs
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action_ref) for action_ref in action_refs)
