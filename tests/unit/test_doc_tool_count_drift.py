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
import types
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_DOCS = REPO_ROOT / "ai_docs"
ALLOWED_SOURCES = {
    "domains/python-refactor/reference.md",  # canonical
    "backlog.md",  # may legitimately reference counts in row descriptions
}
# Subtrees holding transient/generated artifacts that legitimately reference
# the current tool count when capturing repo state at a point in time.
# Reference docs (architecture, mcp-checklist, etc.) remain policed.
# "archive/plans/" and "archive/reports/" cover the same trees once doc-audit's
# 30-day-stable retention rule moves them out of "plans/"/"reports/".
EXCLUDED_SUBTREES = ("plans/", "reports/", "archive/plans/", "archive/reports/")
# Counts at or above this are server-wide totals, not per-category subsets.
# The complete catalog is comfortably above 50 while each category remains
# below it, so the threshold separates server-wide totals from category counts.
SERVER_WIDE_THRESHOLD = 50
PATTERN = re.compile(r"\b(\d+) (?:tools|available)\b")


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
# "96-tool reference", "91 available". Per-category counts (e.g. "Analysis (18
# tools)") fall under SERVER_WIDE_THRESHOLD and are intentionally ignored.
# "available" is matched standalone (no "tools" required) because a prior drift
# ("## Tools Reference (91 available)" in deep-review-refactor.md) evaded a
# tools-suffix-only regex for a full audit cycle before being caught.
_LIVE_COUNT_RE = re.compile(r"\b(\d+)[ -](?:MCP )?(?:tools?|available)\b")

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


def test_server_wide_counts_agree_with_complete_catalog() -> None:
    """Every server-wide tool-count claim equals the complete catalog size.

    Profiles advertise bounded subsets, so the declarative registration catalog
    is the source of truth for docs that state the complete total.
    """
    from python_refactor_mcp import server  # noqa: PLC0415
    from python_refactor_mcp.tool_registry import TOOL_RECORDS  # noqa: PLC0415

    catalog_count = len(TOOL_RECORDS) + len(server.EXPLICIT_TOOL_RECORDS)

    offenders: list[tuple[str, int, int, str]] = []
    for path in _policed_doc_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in _LIVE_COUNT_RE.finditer(line):
                value = int(match.group(1))
                if value >= SERVER_WIDE_THRESHOLD and value != catalog_count:
                    offenders.append((rel, lineno, value, line.strip()))

    assert offenders == [], (
        f"Server-wide tool counts disagree with the catalog ({catalog_count} tools). "
        f"Update each to {catalog_count} (or move point-in-time counts under plans/ reports/ "
        f"or CHANGELOG):\n  "
        + "\n  ".join(f"{rel}:{lineno}: found {value} — {line}" for rel, lineno, value, line in offenders)
    )


def _catalog_tool_count() -> int:
    from python_refactor_mcp import server  # noqa: PLC0415
    from python_refactor_mcp.tool_registry import TOOL_RECORDS  # noqa: PLC0415

    return len(TOOL_RECORDS) + len(server.EXPLICIT_TOOL_RECORDS)


def _assert_categories_consistent(
    *, source: str, total: int, live: int, categories: list[tuple[str, int, int]]
) -> None:
    """Assert per-category declared counts match listed tools, sum to the file
    total, and that the total equals the live MCP surface."""
    mismatched = [(name, declared, actual) for name, declared, actual in categories if declared != actual]
    assert mismatched == [], (
        f"{source}: category header count disagrees with the tools listed under it:\n  "
        + "\n  ".join(f"{name}: header says {declared}, lists {actual}" for name, declared, actual in mismatched)
    )
    summed = sum(declared for _, declared, _ in categories)
    assert summed == total, f"{source}: category counts sum to {summed} but the file total is {total}"
    assert total == live, f"{source}: stated total {total} != live MCP surface {live}"


def test_reference_md_category_counts_consistent() -> None:
    """Reference category counts sum to the complete catalog."""
    catalog_count = _catalog_tool_count()
    lines = (AI_DOCS / "domains" / "python-refactor" / "reference.md").read_text(encoding="utf-8").splitlines()

    total: int | None = None
    categories: list[tuple[str, int, int]] = []
    for idx, line in enumerate(lines):
        total_match = re.match(r"## Tool (?:Surface|Catalog) \((\d+) tools\)", line)
        if total_match:
            total = int(total_match.group(1))
            continue
        cat_match = re.match(r"### (.+?) \((\d+) tools\)", line)
        if not cat_match:
            continue
        name, declared = cat_match.group(1), int(cat_match.group(2))
        # Tool names are backtick-delimited on the line(s) until the next blank/header.
        listed = 0
        j = idx + 1
        while j < len(lines) and lines[j].strip() and not lines[j].startswith("#"):
            listed += len(re.findall(r"`[^`]+`", lines[j]))
            j += 1
        categories.append((name, declared, listed))

    assert total is not None, "reference.md is missing its '## Tool Catalog (N tools)' header"
    _assert_categories_consistent(source="reference.md", total=total, live=catalog_count, categories=categories)


def test_docs_tool_reference_category_counts_consistent() -> None:
    """docs/tool-reference.md: `## Cat (N)` == table rows under it, summing to the
    'N MCP tools' header total, which equals the complete catalog."""
    catalog_count = _catalog_tool_count()
    lines = (REPO_ROOT / "docs" / "tool-reference.md").read_text(encoding="utf-8").splitlines()

    header_match = re.search(r"(\d+)(?: MCP tools|-tool catalog)", "\n".join(lines))
    assert header_match is not None, "docs/tool-reference.md is missing its complete-catalog count"
    total = int(header_match.group(1))

    categories: list[tuple[str, int, int]] = []
    for idx, line in enumerate(lines):
        cat_match = re.match(r"## (.+?) \((\d+)\)", line)
        if not cat_match:
            continue
        name, declared = cat_match.group(1), int(cat_match.group(2))
        # Count markdown table data rows (`| `tool` | ... |`) until the next category.
        rows = 0
        j = idx + 1
        while j < len(lines) and not lines[j].startswith("## "):
            if re.match(r"\|\s*`[^`]+`\s*\|", lines[j]):
                rows += 1
            j += 1
        categories.append((name, declared, rows))

    _assert_categories_consistent(
        source="docs/tool-reference.md",
        total=total,
        live=catalog_count,
        categories=categories,
    )


def _render_return_annotation(annotation: object) -> str:
    """Render a live return annotation in the compact docs-table form."""
    origin = get_origin(annotation)
    if origin is types.UnionType:
        return " | ".join(_render_return_annotation(arg) for arg in get_args(annotation))
    if origin is not None:
        name = getattr(origin, "__name__", str(origin))
        args = ", ".join(_render_return_annotation(arg) for arg in get_args(annotation))
        return f"{name}[{args}]"
    if annotation is type(None):
        return "None"
    return getattr(annotation, "__name__", str(annotation))


def test_docs_tool_reference_returns_match_live_annotations() -> None:
    """Every documented return contract matches its registered callable."""
    from python_refactor_mcp import server  # noqa: PLC0415
    from python_refactor_mcp.tool_registry import TOOL_RECORDS  # noqa: PLC0415

    live = {
        record.func.__name__: _render_return_annotation(get_type_hints(record.func)["return"])
        for record in (*TOOL_RECORDS, *server.EXPLICIT_TOOL_RECORDS)
    }
    row_pattern = re.compile(r"^\| `([^`]+)` \|.*\| `([^`]+)` \|$")
    documented: dict[str, str] = {}
    reference = REPO_ROOT / "docs" / "tool-reference.md"
    for line in reference.read_text(encoding="utf-8").splitlines():
        match = row_pattern.match(line)
        if match:
            documented[match.group(1)] = match.group(2).replace("\\|", "|")

    assert documented.keys() == live.keys(), (
        f"docs/tool-reference.md tool names differ from the live catalog; "
        f"missing={sorted(live.keys() - documented.keys())}, "
        f"extra={sorted(documented.keys() - live.keys())}"
    )
    mismatches = {
        name: {"documented": documented[name], "live": live[name]}
        for name in live
        if documented[name] != live[name]
    }
    assert mismatches == {}, f"Documented return contracts differ from live annotations: {mismatches}"
