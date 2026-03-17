"""Navigation tool placeholders for Stage 1."""

from __future__ import annotations


async def call_hierarchy(
    file_path: str,
    line: int,
    character: int,
    direction: str = "both",
    depth: int = 1,
) -> str:
    """Get incoming and outgoing call hierarchy data."""
    return "Not yet implemented"


async def goto_definition(file_path: str, line: int, character: int) -> str:
    """Navigate to symbol definitions from a source position."""
    return "Not yet implemented"
