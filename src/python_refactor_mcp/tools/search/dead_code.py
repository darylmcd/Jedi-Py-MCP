"""Detect dead code candidates using diagnostics and reference counts."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    DeadCodeItem,
    Diagnostic,
    PaginatedDeadCode,
    Range,
    ScanFailure,
)

from ._helpers import (
    DIAGNOSTIC_TAG_UNNECESSARY,
    PyrightSearchBackend,
    iter_module_level_symbols,
    resolve_target_files,
    score_dead_code_confidence,
)


def _is_dead_code_diagnostic(diagnostic: Diagnostic) -> bool:
    """Return True if the diagnostic indicates unused/dead code."""
    lowered = diagnostic.message.lower()
    has_unnecessary_tag = DIAGNOSTIC_TAG_UNNECESSARY in diagnostic.tags
    return has_unnecessary_tag or "unused" in lowered or "not accessed" in lowered


def _dead_item_from_diagnostic(diagnostic: Diagnostic) -> DeadCodeItem:
    """Convert a dead-code diagnostic into a DeadCodeItem."""
    lowered = diagnostic.message.lower()
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", diagnostic.message)
    name = quoted[0] if quoted else "unknown"
    reason = "unused diagnostic"
    return DeadCodeItem(
        name=name,
        kind="import" if "import" in lowered else "symbol",
        file_path=diagnostic.file_path,
        range=diagnostic.range,
        reason=reason,
        confidence=score_dead_code_confidence(name, reason),
    )


async def _check_symbol(
    pyright: PyrightSearchBackend,
    sem: asyncio.Semaphore,
    path: Path,
    name: str,
    kind: str,
    symbol_range: Range,
) -> DeadCodeItem | None:
    """Check whether a symbol has external references; return a dead-code item if not."""
    async with sem:
        references = await pyright.get_references(
            str(path),
            symbol_range.start.line,
            symbol_range.start.character,
            False,
        )
    resolved_path = str(path.resolve())
    same_file_count = 0
    has_external = False
    for ref in references:
        ref_path = getattr(ref, "file_path", None)
        if not isinstance(ref_path, str):
            continue
        if ref_path == resolved_path:
            same_file_count += 1
        else:
            has_external = True
            break
    if has_external or same_file_count > 1:
        return None
    reason = "no references"
    return DeadCodeItem(
        name=name,
        kind=kind,
        file_path=resolved_path,
        range=symbol_range,
        reason=reason,
        confidence=score_dead_code_confidence(name, reason),
    )


async def dead_code_detection(
    pyright: PyrightSearchBackend,
    config: ServerConfig,
    file_path: str | None = None,
    exclude_patterns: list[str] | None = None,
    root_path: str | None = None,
    exclude_test_files: bool = True,
    file_paths: list[str] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> PaginatedDeadCode:
    """Detect dead code candidates using diagnostics and reference counts."""
    target_files = resolve_target_files(file_path, file_paths, root_path, config, exclude_test_files)
    target_paths = {str(path.resolve()) for path in target_files}

    dead_items: dict[tuple[str, str, int, int], DeadCodeItem] = {}
    compiled_excludes = [re.compile(pattern) for pattern in (exclude_patterns or [])]

    # Phase 1: Collect diagnostics per target file with bounded concurrency.
    sem = asyncio.Semaphore(10)

    async def _fetch_diags(path: Path) -> list[Diagnostic]:
        if not path.exists():
            return []
        async with sem:
            file_diags = await pyright.get_diagnostics(str(path))
            return [d for d in file_diags if d.file_path in target_paths]

    diag_results = await asyncio.gather(*[_fetch_diags(p) for p in target_files], return_exceptions=True)
    all_diagnostics: list[Diagnostic] = []
    scan_failures: list[ScanFailure] = []
    for path, diag_result in zip(target_files, diag_results, strict=True):
        if isinstance(diag_result, list):
            all_diagnostics.extend(diag_result)
        else:
            scan_failures.append(
                ScanFailure(
                    file_path=str(path.resolve()),
                    phase="diagnostics",
                    error_type=type(diag_result).__name__,
                )
            )

    for diagnostic in all_diagnostics:
        if not _is_dead_code_diagnostic(diagnostic):
            continue
        item = _dead_item_from_diagnostic(diagnostic)
        key = (item.file_path, item.name, item.range.start.line, item.range.start.character)
        dead_items[key] = item

    # Phase 2: Collect symbols and check references with bounded concurrency.
    symbols_to_check: list[tuple[Path, str, str, Range]] = []
    for path in target_files:
        try:
            symbols = iter_module_level_symbols(path, skip_decorated=True)
        except (OSError, SyntaxError, UnicodeError) as exc:
            scan_failures.append(
                ScanFailure(
                    file_path=str(path.resolve()),
                    phase="symbol_scan",
                    error_type=type(exc).__name__,
                )
            )
            continue
        for name, kind, symbol_range in symbols:
            if name == "__all__":
                continue
            if any(pattern.search(name) for pattern in compiled_excludes):
                continue
            symbols_to_check.append((path, name, kind, symbol_range))

    ref_results = await asyncio.gather(
        *[_check_symbol(pyright, sem, p, n, k, r) for p, n, k, r in symbols_to_check],
        return_exceptions=True,
    )
    for (path, name, _kind, _symbol_range), ref_result in zip(
        symbols_to_check, ref_results, strict=True
    ):
        if isinstance(ref_result, DeadCodeItem):
            key = (ref_result.file_path, ref_result.name, ref_result.range.start.line, ref_result.range.start.character)
            dead_items[key] = ref_result
        elif isinstance(ref_result, BaseException):
            scan_failures.append(
                ScanFailure(
                    file_path=str(path.resolve()),
                    phase="references",
                    error_type=type(ref_result).__name__,
                    subject=name,
                )
            )

    # Phase 3: Sort and paginate results.
    all_items = sorted(
        dead_items.values(),
        key=lambda item: (item.file_path, item.name, item.range.start.line, item.range.start.character),
    )
    total_count = len(all_items)
    items = all_items[offset:] if offset > 0 else all_items
    truncated = False
    if limit is not None and limit > 0 and len(items) > limit:
        items = items[:limit]
        truncated = True
    return PaginatedDeadCode(
        items=items,
        total_count=total_count,
        offset=offset,
        truncated=truncated,
        scan_failures=scan_failures,
    )
