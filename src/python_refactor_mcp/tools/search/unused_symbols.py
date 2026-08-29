"""Audit the public export surface for symbols with zero cross-file references.

``unused_symbol_sweep`` is the export-surface complement to
:func:`python_refactor_mcp.tools.search.dead_code.dead_code_detection`. Where
``dead_code_detection`` scans *undecorated* module-level symbols, this sweep
covers the full public API surface — ``__all__``-listed names when an
``__all__`` is present, otherwise every non-underscore module-level name —
*regardless of decoration*, and flags any with no inbound references from
another file. Symbols registered through an external decorator (anything whose
decorator name contains ``mcp`` or ``tool``, e.g. ``@mcp.tool``) are skipped to
avoid false positives, mirroring the rationale behind ``dead_code_detection``'s
blanket decorator skip.

The sweep may be slow on large codebases: it issues one ``get_references`` call
per exported symbol. ``limit`` bounds the response size but not the work done.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import DeadCodeItem, PaginatedDeadCode, Range, ScanFailure

from ._helpers import (
    PyrightSearchBackend,
    resolve_target_files,
    scan_module_level_symbols,
    score_dead_code_confidence,
)


def _is_externally_registered(decorator_names: tuple[str, ...]) -> bool:
    """Return whether a framework-like decorator owns the symbol lifecycle."""
    return any("mcp" in name.lower() or "tool" in name.lower() for name in decorator_names)


async def _check_export_symbol(
    pyright: PyrightSearchBackend,
    sem: asyncio.Semaphore,
    path: Path,
    name: str,
    kind: str,
    symbol_range: Range,
) -> DeadCodeItem | None:
    """Return a dead-code item when an exported symbol has no cross-file references."""
    async with sem:
        references = await pyright.get_references(
            str(path),
            symbol_range.start.line,
            symbol_range.start.character,
            False,
        )
    resolved_path = str(path.resolve())
    for ref in references:
        ref_path = getattr(ref, "file_path", None)
        if isinstance(ref_path, str) and ref_path != resolved_path:
            return None
    return DeadCodeItem(
        name=name,
        kind=kind,
        file_path=resolved_path,
        range=symbol_range,
        reason="no external references",
        confidence=score_dead_code_confidence(name, "no external references"),
    )


async def unused_symbol_sweep(
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
    """Audit the public export surface for symbols with no cross-file references."""
    target_files = resolve_target_files(file_path, file_paths, root_path, config, exclude_test_files)
    compiled_excludes = [re.compile(pattern) for pattern in (exclude_patterns or [])]

    symbols_to_check: list[tuple[Path, str, str, Range]] = []
    scan_failures: list[ScanFailure] = []
    for path in target_files:
        try:
            scan = scan_module_level_symbols(path)
        except (OSError, SyntaxError, UnicodeError) as exc:
            scan_failures.append(
                ScanFailure(
                    file_path=str(path.resolve()),
                    phase="symbol_scan",
                    error_type=type(exc).__name__,
                )
            )
            continue
        for symbol in scan.symbols:
            name = symbol.name
            in_surface = (
                name in scan.explicit_exports
                if scan.explicit_exports is not None
                else not name.startswith("_")
            )
            if name == "__all__" or not in_surface or _is_externally_registered(symbol.decorator_names):
                continue
            if any(pattern.search(name) for pattern in compiled_excludes):
                continue
            symbols_to_check.append((path, name, symbol.kind, symbol.range))

    sem = asyncio.Semaphore(10)
    results = await asyncio.gather(
        *[_check_export_symbol(pyright, sem, p, n, k, r) for p, n, k, r in symbols_to_check],
        return_exceptions=True,
    )

    unused: dict[tuple[str, str, int, int], DeadCodeItem] = {}
    for (path, name, _kind, _symbol_range), result in zip(
        symbols_to_check, results, strict=True
    ):
        if isinstance(result, DeadCodeItem):
            key = (result.file_path, result.name, result.range.start.line, result.range.start.character)
            unused[key] = result
        elif isinstance(result, BaseException):
            scan_failures.append(
                ScanFailure(
                    file_path=str(path.resolve()),
                    phase="references",
                    error_type=type(result).__name__,
                    subject=name,
                )
            )

    all_items = sorted(
        unused.values(),
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
