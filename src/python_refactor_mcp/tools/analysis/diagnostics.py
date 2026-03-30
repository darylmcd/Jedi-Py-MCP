"""Diagnostic analysis tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    Diagnostic,
    DiagnosticSummary,
    PaginatedDiagnosticSummary,
)
from python_refactor_mcp.tools.analysis._protocols import (
    PyrightAnalysisBackend as _PyrightAnalysisBackend,
)
from python_refactor_mcp.util.file_filter import python_files
from python_refactor_mcp.util.shared import apply_limit, diagnostic_key

_VALID_SEVERITIES = {"error", "warning", "information", "hint"}

_apply_limit = apply_limit


def _sort_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    """Return diagnostics sorted by file and source order position."""
    return sorted(
        diagnostics,
        key=lambda item: (
            item.file_path,
            item.range.start.line,
            item.range.start.character,
            item.range.end.line,
            item.range.end.character,
        ),
    )


async def get_diagnostics(
    pyright: _PyrightAnalysisBackend,
    file_path: str | None = None,
    severity_filter: str | None = None,
    limit: int | None = None,
    suppress_codes: list[str] | None = None,
    file_paths: list[str] | None = None,
) -> list[Diagnostic]:
    """Get diagnostics for one file, a batch of files, or the full project."""
    if file_path is not None and file_paths is not None:
        raise ValueError("file_path and file_paths are mutually exclusive")

    normalized_severity: str | None = None
    if severity_filter is not None:
        normalized_severity = severity_filter.strip().lower()
        if normalized_severity not in _VALID_SEVERITIES:
            valid = ", ".join(sorted(_VALID_SEVERITIES))
            raise ValueError(f"Invalid severity_filter '{severity_filter}'. Expected one of: {valid}")

    if file_paths is not None:
        all_diags: list[Diagnostic] = []
        for fp in file_paths:
            all_diags.extend(await pyright.get_diagnostics(fp))
        diagnostics = all_diags
    else:
        diagnostics = await pyright.get_diagnostics(file_path)

    # Deduplicate diagnostics that appear at the same position with the same message.
    seen: dict[tuple[str, int, int, int, int, str, str], Diagnostic] = {}
    for d in diagnostics:
        key = diagnostic_key(d)
        if key not in seen:
            seen[key] = d
    diagnostics = list(seen.values())

    if normalized_severity is not None:
        diagnostics = [
            diagnostic
            for diagnostic in diagnostics
            if diagnostic.severity.strip().lower() == normalized_severity
        ]

    if suppress_codes:
        suppress_set = set(suppress_codes)
        diagnostics = [d for d in diagnostics if d.code not in suppress_set]

    sorted_items = _sort_diagnostics(diagnostics)
    limited, _ = _apply_limit(sorted_items, limit)
    return limited


async def get_workspace_diagnostics(
    pyright: _PyrightAnalysisBackend,
    config: ServerConfig,
    root_path: str | None = None,
    suppress_codes: list[str] | None = None,
    file_paths: list[str] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> PaginatedDiagnosticSummary:
    """Aggregate workspace diagnostics into one summary per file."""
    effective_root = Path(root_path).resolve() if root_path else config.workspace_root
    suppress_set = set(suppress_codes) if suppress_codes else None

    target_files: list[Path] = (
        [Path(p).resolve() for p in file_paths] if file_paths is not None
        else python_files(effective_root)
    )

    # Parallelize with bounded concurrency.
    sem = asyncio.Semaphore(10)

    async def _fetch(path: Path) -> list[Diagnostic]:
        async with sem:
            file_diags = await pyright.get_diagnostics(str(path))
            if suppress_set:
                file_diags = [d for d in file_diags if d.code not in suppress_set]
            return file_diags

    all_results = await asyncio.gather(*[_fetch(p) for p in target_files], return_exceptions=True)
    diagnostics: list[Diagnostic] = []
    for result in all_results:
        if isinstance(result, list):
            diagnostics.extend(result)

    by_file: dict[str, dict[str, int]] = {}
    for diagnostic in diagnostics:
        counts = by_file.setdefault(
            diagnostic.file_path,
            {"error": 0, "warning": 0, "information": 0, "hint": 0},
        )
        severity = diagnostic.severity.strip().lower()
        if severity not in counts:
            severity = "information"
        counts[severity] += 1

    summaries = sorted(
        [
            DiagnosticSummary(
                file_path=file_path,
                error_count=counts["error"],
                warning_count=counts["warning"],
                information_count=counts["information"],
                hint_count=counts["hint"],
                total_count=sum(counts.values()),
            )
            for file_path, counts in by_file.items()
        ],
        key=lambda item: item.file_path,
    )

    total_count = len(summaries)
    if offset > 0:
        summaries = summaries[offset:]
    truncated = False
    if limit is not None and limit > 0 and len(summaries) > limit:
        summaries = summaries[:limit]
        truncated = True

    return PaginatedDiagnosticSummary(
        items=summaries,
        total_count=total_count,
        offset=offset,
        truncated=truncated,
    )
