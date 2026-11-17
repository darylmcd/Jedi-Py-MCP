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


WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SETUP_ACTION_REF = "./.github/actions/setup-python-env"
SETUP_ACTION = REPO_ROOT / ".github" / "actions" / "setup-python-env" / "action.yml"


def _action_refs(text: str) -> list[str]:
    return [
        line.partition("uses:")[2].strip().split(maxsplit=1)[0]
        for line in text.splitlines()
        if "uses:" in line
    ]


def test_hosted_ci_syncs_the_authoritative_lockfile() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    setup_action = SETUP_ACTION.read_text(encoding="utf-8")

    assert "uv sync --locked --all-extras" in setup_action
    assert "pip install" not in setup_action
    assert "pip install" not in workflow
    # Every Windows job validates against the locked environment from the shared setup action.
    windows_jobs = workflow.count("runs-on: windows-latest")
    assert windows_jobs
    assert _action_refs(workflow).count(SETUP_ACTION_REF) == windows_jobs


def test_hosted_ci_actions_are_pinned_to_commits() -> None:
    action_files = [WORKFLOW, *sorted((REPO_ROOT / ".github" / "actions").glob("*/action.yml"))]
    action_refs = [ref for path in action_files for ref in _action_refs(path.read_text(encoding="utf-8"))]
    remote_refs = [ref for ref in action_refs if not ref.startswith("./")]
    local_refs = [ref for ref in action_refs if ref.startswith("./")]

    assert remote_refs
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action_ref) for action_ref in remote_refs)
    assert all((REPO_ROOT / ref / "action.yml").is_file() for ref in local_refs)
