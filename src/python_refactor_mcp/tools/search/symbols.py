"""Search workspace symbols by name across semantic backends."""

from __future__ import annotations

from python_refactor_mcp.models import BackendFailure, SymbolInfo, SymbolSearchResult

from ._helpers import (
    JediSearchBackend,
    PyrightSearchBackend,
    apply_limit_items,
)


def _symbol_sort_key(symbol: SymbolInfo) -> tuple[str, str, int, int, str]:
    """Build stable sort key for symbol search results."""
    return (
        symbol.file_path,
        symbol.name,
        symbol.range.start.line,
        symbol.range.start.character,
        symbol.kind,
    )


async def search_symbols(
    pyright: PyrightSearchBackend,
    jedi: JediSearchBackend,
    query: str,
    limit: int | None = None,
) -> SymbolSearchResult:
    """Search workspace symbols by name across both semantic backends."""
    merged: dict[tuple[str, str, int, int, str], SymbolInfo] = {}
    backend_failures: list[BackendFailure] = []

    try:
        pyright_symbols = await pyright.workspace_symbol(query)
    except Exception as exc:
        backend_failures.append(
            BackendFailure(backend="pyright", operation="workspace_symbol", error_type=type(exc).__name__)
        )
        pyright_symbols = []
    for symbol in pyright_symbols:
        merged[_symbol_sort_key(symbol)] = symbol

    try:
        jedi_symbols = await jedi.search_symbols(query)
    except Exception as exc:
        backend_failures.append(
            BackendFailure(backend="jedi", operation="search_symbols", error_type=type(exc).__name__)
        )
        jedi_symbols = []
    for symbol in jedi_symbols:
        merged.setdefault(_symbol_sort_key(symbol), symbol)

    sorted_items = sorted(merged.values(), key=_symbol_sort_key)
    items = apply_limit_items(sorted_items, limit)
    return SymbolSearchResult(
        items=items,
        total_count=len(sorted_items),
        truncated=len(items) < len(sorted_items),
        backend_failures=backend_failures,
    )
