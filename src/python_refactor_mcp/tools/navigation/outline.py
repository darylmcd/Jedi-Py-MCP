"""Symbol outline, folding ranges, and selection range tools."""

from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import LspFeatureUnsupportedError, ToolInputError
from python_refactor_mcp.models import (
    FoldingRange,
    Position,
    SelectionRangeResult,
    SymbolOutlineItem,
    SymbolOutlineResult,
)
from python_refactor_mcp.util.file_filter import python_files
from python_refactor_mcp.util.shared import apply_limit as _apply_limit

from ._protocols import PyrightNavigationBackend


def _outline_key(item: SymbolOutlineItem) -> tuple[str, int, int, str]:
    """Build a stable sort key for outline items."""
    return (item.file_path, item.selection_range.start.line, item.selection_range.start.character, item.name)


def _range_contains(outer: SymbolOutlineItem, inner: SymbolOutlineItem) -> bool:
    """Return True if *outer*'s range fully contains *inner*'s range."""
    if outer.file_path != inner.file_path:
        return False
    o_start = (outer.range.start.line, outer.range.start.character)
    o_end = (outer.range.end.line, outer.range.end.character)
    i_start = (inner.range.start.line, inner.range.start.character)
    i_end = (inner.range.end.line, inner.range.end.character)
    return o_start <= i_start and i_end <= o_end


def _renest_flattened_symbols(items: list[SymbolOutlineItem]) -> list[SymbolOutlineItem]:
    """Move flattened inner functions into the children of their enclosing scope.

    Pyright's documentSymbol may report nested closures (e.g., ``_work()``
    inside an async method) as top-level siblings.  This function checks
    each function-kind item against others and nests it if its range is
    fully contained within a parent item.
    """
    if len(items) <= 1:
        return items

    # Sort by file then by range start (outermost first).
    sorted_items = sorted(items, key=lambda s: (
        s.file_path, s.range.start.line, s.range.start.character,
        -(s.range.end.line * 10000 + s.range.end.character),
    ))

    top_level: list[SymbolOutlineItem] = []
    nested_ids: set[int] = set()

    for i, item in enumerate(sorted_items):
        if id(item) in nested_ids:
            continue
        # Check if any later item should be nested under this one.
        for j in range(i + 1, len(sorted_items)):
            candidate = sorted_items[j]
            if id(candidate) in nested_ids:
                continue
            if _range_contains(item, candidate) and item is not candidate:
                item.children.append(candidate)
                nested_ids.add(id(candidate))
        top_level.append(item)

    return top_level


def _count_nodes(item: SymbolOutlineItem) -> int:
    """Count *item* plus all of its descendants."""
    return 1 + sum(_count_nodes(child) for child in item.children)


def _prune_to_budget(item: SymbolOutlineItem, budget: int) -> tuple[SymbolOutlineItem, int]:
    """Copy *item* keeping a depth-first prefix of descendants within *budget* (>= 1).

    Returns the pruned copy and the number of nodes it contains.
    """
    used = 1
    kept: list[SymbolOutlineItem] = []
    for child in item.children:
        if used >= budget:
            break
        pruned, count = _prune_to_budget(child, budget - used)
        kept.append(pruned)
        used += count
    return item.model_copy(update={"children": kept}), used


def _apply_node_budget(
    roots: list[SymbolOutlineItem],
    max_nodes: int | None,
) -> tuple[list[SymbolOutlineItem], int, bool]:
    """Keep whole roots until *max_nodes* is spent; prune the crossing root depth-first.

    Returns ``(items, returned_nodes, truncated)``.
    """
    if max_nodes is None:
        return roots, sum(_count_nodes(root) for root in roots), False
    kept: list[SymbolOutlineItem] = []
    used = 0
    for root in roots:
        remaining = max_nodes - used
        if remaining <= 0:
            return kept, used, True
        size = _count_nodes(root)
        if size <= remaining:
            kept.append(root)
            used += size
            continue
        # The crossing root always loses descendants, so the page is truncated.
        pruned, count = _prune_to_budget(root, remaining)
        kept.append(pruned)
        return kept, used + count, True
    return kept, used, False


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


def _require_file(parameter: str, raw_path: str) -> Path:
    """Resolve an explicitly requested outline file or reject it as caller input."""
    path = Path(raw_path).resolve()
    if not path.is_file():
        raise ToolInputError(f"{parameter} is not an existing file: {raw_path}")
    return path


async def get_symbol_outline(
    pyright: PyrightNavigationBackend,
    config: ServerConfig,
    file_path: str | None = None,
    kind_filter: list[str] | None = None,
    name_pattern: str | None = None,
    limit: int | None = None,
    root_path: str | None = None,
    file_paths: list[str] | None = None,
    offset: int = 0,
    max_nodes: int | None = None,
) -> SymbolOutlineResult:
    """Return a filtered symbol outline for one file, batch, or full workspace.

    ``limit`` bounds root items; ``max_nodes`` bounds roots plus descendants.
    """
    if file_path is not None and file_paths is not None:
        raise ToolInputError("file_path and file_paths are mutually exclusive")
    if max_nodes is not None and max_nodes < 1:
        raise ToolInputError("max_nodes must be greater than or equal to 1")

    if file_paths is not None:
        candidate_files = [_require_file("file_paths", p) for p in file_paths]
    elif file_path is not None:
        candidate_files = [_require_file("file_path", file_path)]
    elif root_path:
        effective_root = Path(root_path).resolve()
        if not effective_root.is_dir():
            raise ToolInputError(f"root_path is not an existing directory: {root_path}")
        candidate_files = python_files(effective_root)
    else:
        candidate_files = python_files(config.workspace_root)

    normalized_kinds = {kind.strip().lower() for kind in kind_filter} if kind_filter else None
    compiled_pattern: re.Pattern[str] | None = None
    if name_pattern:
        try:
            compiled_pattern = re.compile(name_pattern)
        except re.error as exc:
            raise ToolInputError(f"name_pattern is not a valid regex '{name_pattern}': {exc}") from exc

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
        async with sem:
            symbols = await pyright.get_document_symbols(str(path))
            return _collect_matching(symbols)

    all_results = await asyncio.gather(*[_fetch(p) for p in candidate_files], return_exceptions=True)
    outlines: list[SymbolOutlineItem] = []
    for result in all_results:
        if isinstance(result, list):
            outlines.extend(result)

    # Re-nest flattened inner functions: Pyright's documentSymbol can report
    # nested closures (e.g., _work() inside async methods) as top-level
    # symbols.  Move items whose range is fully contained within another
    # item's range into that item's children list.
    outlines = _renest_flattened_symbols(outlines)

    sorted_items = sorted(outlines, key=_outline_key)
    total_count = len(sorted_items)
    total_nodes = sum(_count_nodes(item) for item in sorted_items)
    if offset > 0:
        sorted_items = sorted_items[offset:]
    limited, root_truncated = _apply_limit(sorted_items, limit)
    bounded, returned_nodes, node_truncated = _apply_node_budget(limited, max_nodes)
    return SymbolOutlineResult(
        items=bounded,
        total_count=total_count,
        offset=offset,
        truncated=root_truncated or node_truncated,
        total_nodes=total_nodes,
        returned_nodes=returned_nodes,
    )


async def get_folding_ranges(
    pyright: PyrightNavigationBackend,
    file_path: str,
) -> list[FoldingRange]:
    """Return foldable ranges for a file in deterministic order.

    Falls back to AST-derived ranges when Pyright does not implement
    ``textDocument/foldingRange`` or returns no ranges.
    """
    try:
        ranges = await pyright.get_folding_ranges(file_path)
    except LspFeatureUnsupportedError:
        ranges = []
    if not ranges:
        ranges = _ast_folding_ranges(file_path)
    return sorted(ranges, key=lambda item: (item.start_line, item.end_line, item.kind or ""))


async def selection_range(
    pyright: PyrightNavigationBackend,
    file_path: str,
    positions: list[Position],
) -> list[SelectionRangeResult]:
    """Return nested selection ranges for one or more source positions."""
    if not positions:
        raise ToolInputError("positions must contain at least one position")
    return await pyright.get_selection_range(file_path, positions)
