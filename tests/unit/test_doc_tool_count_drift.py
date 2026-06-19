"""Regression: keep server-wide tool counts in a single source.

History: between PR #29 (88 tools) and PR #36 (91 tools), four documentation
files duplicated the server-wide count. Three drifted across releases; PR #37
fixed `reference.md` but missed `architecture.md`, `mcp-checklist.md`, and
`deep-review-refactor.md`.

Policy: ``ai_docs/domains/python-refactor/reference.md`` is the single source
for the categorized tool surface. Other docs should point at it, not duplicate
the count. This test fails when a doc outside that single source duplicates the
server-wide count.

Per-category counts (e.g. ``Analysis (17 tools)``) are not policed here — they
appear legitimately in ``deep-review-refactor.md`` as a per-category index of
prompt phases. The threshold below targets server-wide counts only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_DOCS = REPO_ROOT / "ai_docs"
ALLOWED_SOURCES = {
    "domains/python-refactor/reference.md",  # canonical
    "backlog.md",  # may legitimately reference counts in row descriptions
}
# Subtrees holding transient/generated artifacts that legitimately reference
# the current tool count when capturing repo state at a point in time.
# Reference docs (architecture, mcp-checklist, etc.) remain policed.
EXCLUDED_SUBTREES = ("plans/", "reports/")
# Counts at or above this are server-wide totals, not per-category subsets.
# Today the server has 91 tools and the largest category (Refactoring) has 32;
# 50 is comfortably between them and well below general LLM "tool sprawl"
# thresholds (e.g. mcp_best_practices.md's "30-40 tools" guidance).
SERVER_WIDE_THRESHOLD = 50
PATTERN = re.compile(r"\b(\d+) tools\b")


def test_no_server_wide_tool_count_drift() -> None:
    offenders: list[tuple[str, int, str]] = []
    for path in AI_DOCS.rglob("*.md"):
        rel = path.relative_to(AI_DOCS).as_posix()
        if rel in ALLOWED_SOURCES:
            continue
        if any(rel.startswith(prefix) for prefix in EXCLUDED_SUBTREES):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in PATTERN.finditer(line):
                if int(match.group(1)) >= SERVER_WIDE_THRESHOLD:
                    offenders.append((rel, lineno, line.strip()))
    assert offenders == [], (
        "Server-wide tool counts duplicated outside reference.md — point at "
        "ai_docs/domains/python-refactor/reference.md instead of duplicating "
        "the count:\n  "
        + "\n  ".join(f"{rel}:{lineno}: {line}" for rel, lineno, line in offenders)
    )


# Matches server-wide tool-count claims in prose: "96 tools", "96 MCP tools",
# "96-tool reference". Per-category counts (e.g. "Analysis (18 tools)") fall
# under SERVER_WIDE_THRESHOLD and are intentionally ignored.
_LIVE_COUNT_RE = re.compile(r"\b(\d+)[ -](?:MCP )?tools?\b")

# Directories of current-state docs whose server-wide counts must match reality.
# ``plans/`` and ``reports/`` hold point-in-time snapshots; CHANGELOG.md narrates
# historical per-release counts ("87 → 88 tools") — both are excluded.
_POLICED_DOC_DIRS = ("ai_docs", "docs")
_POLICED_ROOT_FILES = ("README.md", ".ai-doc-audit.md")
_EXCLUDED_PATH_SEGMENTS = {"plans", "reports"}


def _policed_doc_files() -> list[Path]:
    files: list[Path] = []
    for rel_dir in _POLICED_DOC_DIRS:
        for path in (REPO_ROOT / rel_dir).rglob("*.md"):
            parts = set(path.relative_to(REPO_ROOT).parts)
            if parts & _EXCLUDED_PATH_SEGMENTS:
                continue
            files.append(path)
    for name in _POLICED_ROOT_FILES:
        candidate = REPO_ROOT / name
        if candidate.exists():
            files.append(candidate)
    return files


@pytest.mark.asyncio
async def test_server_wide_counts_agree_with_live_surface() -> None:
    """Every server-wide tool-count claim in current-state docs equals len(tools).

    This is the cross-file agreement gate: the live MCP surface is the single
    source of truth, and any doc that states the total (README, reference.md,
    docs/tool-reference.md, .ai-doc-audit.md, ...) must match it. Catches the
    drift class where a tool is added but a reference point is left stale.
    """
    from python_refactor_mcp import server  # noqa: PLC0415

    live = len(await server.mcp.list_tools())

    offenders: list[tuple[str, int, int, str]] = []
    for path in _policed_doc_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in _LIVE_COUNT_RE.finditer(line):
                value = int(match.group(1))
                if value >= SERVER_WIDE_THRESHOLD and value != live:
                    offenders.append((rel, lineno, value, line.strip()))

    assert offenders == [], (
        f"Server-wide tool counts disagree with the live surface ({live} tools). "
        f"Update each to {live} (or move point-in-time counts under plans/ reports/ "
        f"or CHANGELOG):\n  "
        + "\n  ".join(f"{rel}:{lineno}: found {value} — {line}" for rel, lineno, value, line in offenders)
    )
