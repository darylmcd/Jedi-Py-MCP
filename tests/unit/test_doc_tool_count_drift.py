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

AI_DOCS = Path(__file__).resolve().parents[2] / "ai_docs"
ALLOWED_SOURCES = {
    "domains/python-refactor/reference.md",  # canonical
    "backlog.md",  # may legitimately reference counts in row descriptions
}
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
