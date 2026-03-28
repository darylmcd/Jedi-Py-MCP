"""Search workspace symbols by name across semantic backends."""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

from python_refactor_mcp.models import SymbolInfo

from ._helpers import (
    apply_limit_items,
    JediSearchBackend,
    PyrightSearchBackend,
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
) -> list[SymbolInfo]:
    """Search workspace symbols by name across both semantic backends."""
    merged: dict[tuple[str, str, int, int, str], SymbolInfo] = {}

    try:
        pyright_symbols = await pyright.workspace_symbol(query)
    except Exception:
        _LOGGER.debug("pyright workspace_symbol failed for query=%s", query, exc_info=True)
        pyright_symbols = []
    for symbol in pyright_symbols:
        merged[_symbol_sort_key(symbol)] = symbol

    try:
        jedi_symbols = await jedi.search_symbols(query)
    except Exception:
        _LOGGER.debug("jedi search_symbols failed for query=%s", query, exc_info=True)
        jedi_symbols = []
    for symbol in jedi_symbols:
        merged.setdefault(_symbol_sort_key(symbol), symbol)

    sorted_items = sorted(merged.values(), key=_symbol_sort_key)
    return apply_limit_items(sorted_items, limit)
