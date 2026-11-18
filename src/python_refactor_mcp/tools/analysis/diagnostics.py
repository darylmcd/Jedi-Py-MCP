"""Diagnostic analysis tools."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import PyrightError, ToolInputError
from python_refactor_mcp.models import (
    Diagnostic,
    DiagnosticSummary,
    PaginatedDiagnosticSummary,
    ScanFailure,
)
from python_refactor_mcp.tools.analysis._protocols import (
    PyrightAnalysisBackend as _PyrightAnalysisBackend,
)
from python_refactor_mcp.util.file_filter import python_files
from python_refactor_mcp.util.shared import apply_limit, diagnostic_key

_SCAN_CONCURRENCY = 10
_VALID_SEVERITIES = {"error", "warning", "information", "hint"}

_apply_limit = apply_limit

_MAX_NAMED_FAILURES = 3


async def _collect_diagnostics(
    pyright: _PyrightAnalysisBackend,
    target_files: Sequence[Path],
    *,
    close_opened: bool,
) -> tuple[list[Diagnostic], list[ScanFailure]]:
    """Pull the diagnostics of ``target_files`` in one batch: the shared core of both workspace scans.

    One resync of the open documents, then bounded-concurrency pulls. A per-file failure
    becomes a :class:`ScanFailure`; cancellation propagates.
    """
    results = await pyright.get_diagnostics_many(
        [str(path) for path in target_files], concurrency=_SCAN_CONCURRENCY, close_opened=close_opened
    )
    diagnostics: list[Diagnostic] = []
    failures: list[ScanFailure] = []
    for path, result in zip(target_files, results, strict=True):
        if isinstance(result, list):
            diagnostics.extend(result)
        else:
            failures.append(
                ScanFailure(file_path=str(path), phase="diagnostics", error_type=type(result).__name__)
            )
    return diagnostics, failures


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
    *,
    config: ServerConfig | None = None,
) -> list[Diagnostic]:
    """Get diagnostics for one file, a batch of files, or (neither given) every Python file of the workspace.

    The workspace form needs ``config`` (its root is the scan scope) and raises
    :class:`PyrightError` when any file's diagnostics cannot be read: a partial list would
    read as clean. ``get_workspace_diagnostics`` is the tolerant alternative.
    """
    if file_path is not None and file_paths is not None:
        raise ToolInputError("file_path and file_paths are mutually exclusive (parameters: file_path, file_paths)")

    if severity_filter is not None and severity_filter not in _VALID_SEVERITIES:
        valid = ", ".join(sorted(_VALID_SEVERITIES))
        raise ToolInputError(
            f"Invalid severity_filter '{severity_filter}'. Expected one of: {valid} (parameter: severity_filter)"
        )

    if file_paths is not None:
        # Sequential and fail-fast by contract: the first failing file raises its error.
        all_diags: list[Diagnostic] = []
        for result in await pyright.get_diagnostics_many(file_paths, stop_on_error=True):
            if isinstance(result, Exception):
                raise result
            all_diags.extend(result)
        diagnostics = all_diags
    elif file_path is not None:
        diagnostics = await pyright.get_diagnostics(file_path)
    else:
        if config is None:
            raise ValueError("config is required to scan the workspace when no file is given")
        target_files = python_files(config.workspace_root)
        diagnostics, failures = await _collect_diagnostics(pyright, target_files, close_opened=True)
        if failures:
            named = ", ".join(
                f"{failure.file_path} ({failure.error_type})" for failure in failures[:_MAX_NAMED_FAILURES]
            )
            more = f", and {len(failures) - _MAX_NAMED_FAILURES} more" if len(failures) > _MAX_NAMED_FAILURES else ""
            raise PyrightError(
                f"Diagnostics unavailable for {len(failures)} of {len(target_files)} files: {named}{more}. "
                "Use get_workspace_diagnostics for a scan that tolerates unreadable files."
            )

    # Deduplicate diagnostics that appear at the same position with the same message.
    seen: dict[tuple[str, int, int, int, int, str, str], Diagnostic] = {}
    for d in diagnostics:
        key = diagnostic_key(d)
        if key not in seen:
            seen[key] = d
    diagnostics = list(seen.values())

    if severity_filter is not None:
        diagnostics = [
            diagnostic
            for diagnostic in diagnostics
            if diagnostic.severity.strip().lower() == severity_filter
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
    directory: str | None = None,
    suppress_codes: list[str] | None = None,
    file_paths: list[str] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> PaginatedDiagnosticSummary:
    """Aggregate workspace diagnostics into one summary per file."""
    effective_root = Path(directory).resolve() if directory else config.workspace_root
    suppress_set = set(suppress_codes) if suppress_codes else None

    target_files: list[Path] = (
        [Path(p).resolve() for p in file_paths] if file_paths is not None
        else python_files(effective_root)
    )

    diagnostics, scan_failures = await _collect_diagnostics(
        pyright, target_files, close_opened=False
    )
    if suppress_set is not None:
        diagnostics = [d for d in diagnostics if d.code not in suppress_set]

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
        scan_failures=scan_failures,
    )
