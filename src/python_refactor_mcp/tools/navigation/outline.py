"""Symbol outline, folding ranges, and selection range tools."""

from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    FoldingRange,
    Position,
    SelectionRangeResult,
    SymbolOutlineItem,
)
from python_refactor_mcp.util.file_filter import python_files
from python_refactor_mcp.util.shared import apply_limit as _apply_limit

from ._protocols import _PyrightNavigationBackend


def _outline_key(item: SymbolOutlineItem) -> tuple[str, int, int, str]:
    """Build a stable sort key for outline items."""
    return (item.file_path, item.selection_range.start.line, item.selection_range.start.character, item.name)


def _ast_folding_ranges(file_path: str) -> list[FoldingRange]:
    """Generate folding ranges from AST compound statements as a fallback."""
    try:
        source = Path(file_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []

    ranges: list[FoldingRange] = []

    _FOLDABLE = (
        ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
        ast.If, ast.For, ast.While, ast.With, ast.AsyncWith, ast.AsyncFor,
        ast.Try,
    )

    for node in ast.walk(tree):
        if isinstance(node, _FOLDABLE):
            end_lineno = getattr(node, "end_lineno", None)
            if end_lineno is not None and end_lineno > node.lineno:
                ranges.append(FoldingRange(
                    start_line=node.lineno - 1,
                    end_line=end_lineno - 1,
                    kind="region",
                ))

    # Group consecutive imports at module level.
    if hasattr(tree, "body") and tree.body:
        import_start: int | None = None
        import_end: int | None = None
        for stmt in tree.body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                if import_start is None:
                    import_start = stmt.lineno - 1
                import_end = (getattr(stmt, "end_lineno", stmt.lineno) or stmt.lineno) - 1
            else:
                if import_start is not None and import_end is not None and import_end > import_start:
                    ranges.append(FoldingRange(start_line=import_start, end_line=import_end, kind="imports"))
                import_start = None
                import_end = None
        if import_start is not None and import_end is not None and import_end > import_start:
            ranges.append(FoldingRange(start_line=import_start, end_line=import_end, kind="imports"))

    return ranges


async def get_symbol_outline(
    pyright: _PyrightNavigationBackend,
    config: ServerConfig,
    file_path: str | None = None,
    kind_filter: list[str] | None = None,
    name_pattern: str | None = None,
    limit: int | None = None,
    root_path: str | None = None,
    file_paths: list[str] | None = None,
    offset: int = 0,
) -> list[SymbolOutlineItem]:
    """Return a filtered symbol outline for one file, batch, or full workspace."""
    if file_path is not None and file_paths is not None:
        raise ValueError("file_path and file_paths are mutually exclusive")

    effective_root = Path(root_path).resolve() if root_path else config.workspace_root
    if file_paths is not None:
        candidate_files = [Path(p).resolve() for p in file_paths]
    elif file_path is not None:
        candidate_files = [Path(file_path).resolve()]
    else:
        candidate_files = python_files(effective_root)

    normalized_kinds = {kind.strip().lower() for kind in kind_filter} if kind_filter else None
    compiled_pattern: re.Pattern[str] | None = None
    if name_pattern:
        try:
            compiled_pattern = re.compile(name_pattern)
        except re.error as exc:
            raise ValueError(f"Invalid name_pattern regex '{name_pattern}': {exc}") from exc

    def _collect_matching(items: list[SymbolOutlineItem]) -> list[SymbolOutlineItem]:
        """Recursively collect items matching the active kind/name filters."""
        result: list[SymbolOutlineItem] = []
        for item in items:
            matches_kind = normalized_kinds is None or item.kind.strip().lower() in normalized_kinds
            matches_name = compiled_pattern is None or compiled_pattern.search(item.name) is not None
            if matches_kind and matches_name:
                result.append(item)
            result.extend(_collect_matching(item.children))
        return result

    # Parallelize with bounded concurrency for workspace-wide scans.
    sem = asyncio.Semaphore(10)

    async def _fetch(path: Path) -> list[SymbolOutlineItem]:
        if not path.is_file():
            return []
        async with sem:
            symbols = await pyright.get_document_symbols(str(path))
            return _collect_matching(symbols)

    all_results = await asyncio.gather(*[_fetch(p) for p in candidate_files], return_exceptions=True)
    outlines: list[SymbolOutlineItem] = []
    for result in all_results:
        if isinstance(result, list):
            outlines.extend(result)

    sorted_items = sorted(outlines, key=_outline_key)
    if offset > 0:
        sorted_items = sorted_items[offset:]
    limited, _ = _apply_limit(sorted_items, limit)
    return limited


async def get_folding_ranges(
    pyright: _PyrightNavigationBackend,
    file_path: str,
) -> list[FoldingRange]:
    """Return foldable ranges for a file in deterministic order."""
    ranges = await pyright.get_folding_ranges(file_path)
    if not ranges:
        ranges = _ast_folding_ranges(file_path)
    return sorted(ranges, key=lambda item: (item.start_line, item.end_line, item.kind or ""))


async def selection_range(
    pyright: _PyrightNavigationBackend,
    file_path: str,
    positions: list[Position],
) -> list[SelectionRangeResult]:
    """Return nested selection ranges for one or more source positions."""
    if not positions:
        raise ValueError("positions must contain at least one position")
    return await pyright.get_selection_range(file_path, positions)
