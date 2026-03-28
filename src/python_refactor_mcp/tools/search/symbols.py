"""Search workspace symbols by name across semantic backends."""

from __future__ import annotations

from python_refactor_mcp.models import SymbolInfo

from ._helpers import (
    _apply_limit,
    _JediSearchBackend,
    _PyrightSearchBackend,
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
    pyright: _PyrightSearchBackend,
    jedi: _JediSearchBackend,
    query: str,
    limit: int | None = None,
) -> list[SymbolInfo]:
    """Search workspace symbols by name across both semantic backends."""
    merged: dict[tuple[str, str, int, int, str], SymbolInfo] = {}

    try:
        pyright_symbols = await pyright.workspace_symbol(query)
    except Exception:
        pyright_symbols = []
    for symbol in pyright_symbols:
        merged[_symbol_sort_key(symbol)] = symbol

    try:
        jedi_symbols = await jedi.search_symbols(query)
    except Exception:
        jedi_symbols = []
    for symbol in jedi_symbols:
        merged.setdefault(_symbol_sort_key(symbol), symbol)

    sorted_items = sorted(merged.values(), key=_symbol_sort_key)
    return _apply_limit(sorted_items, limit)
