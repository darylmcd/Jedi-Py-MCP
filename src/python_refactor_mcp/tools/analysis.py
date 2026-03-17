"""Analysis tool placeholders for Stage 1."""

from __future__ import annotations


async def find_references(
    file_path: str,
    line: int,
    character: int,
    include_declaration: bool = True,
) -> str:
    """Find symbol references via analysis backends."""
    return "Not yet implemented"


async def get_type_info(file_path: str, line: int, character: int) -> str:
    """Get type information for a symbol position."""
    return "Not yet implemented"


async def get_diagnostics(file_path: str | None = None, severity_filter: str | None = None) -> str:
    """Get diagnostics for one file or the full project."""
    return "Not yet implemented"
