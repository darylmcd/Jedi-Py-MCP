"""Shared helpers, protocols, and constants used across search submodules."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from python_refactor_mcp.models import (
    Diagnostic,
    ImportSuggestion,
    Location,
    Range,
    SymbolInfo,
)
from python_refactor_mcp.util.file_filter import python_files as _filtered_python_files

_DIAGNOSTIC_TAG_UNNECESSARY = 1


class _PyrightSearchBackend(Protocol):
    """Protocol describing Pyright search methods used by this module."""

    async def get_references(
        self,
        file_path: str,
        line: int,
        char: int,
        include_declaration: bool,
    ) -> list[Location]:
        """Return references for a symbol position."""
        ...

    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]:
        """Return diagnostics for one file or the full workspace."""
        ...

    async def get_code_actions(
        self,
        file_path: str,
        range_value: Range,
        diagnostics: list[Diagnostic],
    ) -> list[dict[str, object]]:
        """Return code action candidates for a range."""
        ...

    async def workspace_symbol(self, query: str) -> list[SymbolInfo]:
        """Search workspace symbols by query string."""
        ...


class _JediSearchBackend(Protocol):
    """Protocol describing Jedi search methods used by this module."""

    async def search_names(self, symbol: str) -> list[ImportSuggestion]:
        """Search names and convert them into import suggestions."""
        ...

    async def search_symbols(self, query: str) -> list[SymbolInfo]:
        """Search project symbols by query string."""
        ...


def _python_files(root: Path) -> list[Path]:
    """Return Python files below a root path in stable order, excluding common non-project dirs."""
    return _filtered_python_files(root)


def _range_sort_key(range_value: Range) -> tuple[int, int, int, int]:
    """Build stable sort key for model ranges."""
    return (
        range_value.start.line,
        range_value.start.character,
        range_value.end.line,
        range_value.end.character,
    )


def _apply_limit[T](items: list[T], limit: int | None) -> list[T]:
    """Apply an optional positive limit to list-style tool results."""
    from python_refactor_mcp.util.shared import apply_limit  # noqa: PLC0415

    limited, _ = apply_limit(items, limit)
    return limited


def _name_position(line_text: str, default_col: int, name: str) -> int:
    """Find a symbol name offset in a source line with fallback to default."""
    index = line_text.find(name, max(default_col, 0))
    if index >= 0:
        return index
    return default_col
