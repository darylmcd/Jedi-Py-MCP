"""Diagnostic analysis tools."""

from __future__ import annotations

from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    Diagnostic,
    DiagnosticSummary,
)
from python_refactor_mcp.tools.analysis._protocols import (
    PyrightAnalysisBackend as _PyrightAnalysisBackend,
)
from python_refactor_mcp.util.file_filter import python_files
from python_refactor_mcp.util.shared import apply_limit

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
) -> list[Diagnostic]:
    """Get diagnostics for one file or the full project."""
    normalized_severity: str | None = None
    if severity_filter is not None:
        normalized_severity = severity_filter.strip().lower()
        if normalized_severity not in _VALID_SEVERITIES:
            valid = ", ".join(sorted(_VALID_SEVERITIES))
            raise ValueError(f"Invalid severity_filter '{severity_filter}'. Expected one of: {valid}")

    diagnostics = await pyright.get_diagnostics(file_path)
    if normalized_severity is not None:
        diagnostics = [
            diagnostic
            for diagnostic in diagnostics
            if diagnostic.severity.strip().lower() == normalized_severity
        ]

    sorted_items = _sort_diagnostics(diagnostics)
    limited, _ = _apply_limit(sorted_items, limit)
    return limited


async def get_workspace_diagnostics(
    pyright: _PyrightAnalysisBackend,
    config: ServerConfig,
    root_path: str | None = None,
) -> list[DiagnosticSummary]:
    """Aggregate workspace diagnostics into one summary per file."""
    effective_root = Path(root_path).resolve() if root_path else config.workspace_root
    diagnostics: list[Diagnostic] = []
    for path in python_files(effective_root):
        diagnostics.extend(await pyright.get_diagnostics(str(Path(path).resolve())))
    by_file: dict[str, dict[str, int]] = {}

    for diagnostic in diagnostics:
        counts = by_file.setdefault(
            diagnostic.file_path,
            {
                "error": 0,
                "warning": 0,
                "information": 0,
                "hint": 0,
            },
        )
        severity = diagnostic.severity.strip().lower()
        if severity not in counts:
            severity = "information"
        counts[severity] += 1

    summaries = [
        DiagnosticSummary(
            file_path=file_path,
            error_count=counts["error"],
            warning_count=counts["warning"],
            information_count=counts["information"],
            hint_count=counts["hint"],
            total_count=sum(counts.values()),
        )
        for file_path, counts in by_file.items()
    ]
    return sorted(summaries, key=lambda item: item.file_path)
