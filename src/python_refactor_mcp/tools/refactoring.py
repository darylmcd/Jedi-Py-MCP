"""Refactoring tool placeholders for Stage 1."""

from __future__ import annotations


async def rename_symbol(
    file_path: str,
    line: int,
    character: int,
    new_name: str,
    apply: bool = False,
) -> str:
    """Rename a symbol at the provided position."""
    return "Not yet implemented"


async def extract_method(
    file_path: str,
    start_line: int,
    start_character: int,
    end_line: int,
    end_character: int,
    method_name: str,
    apply: bool = False,
) -> str:
    """Extract selected code into a method."""
    return "Not yet implemented"


async def extract_variable(
    file_path: str,
    start_line: int,
    start_character: int,
    end_line: int,
    end_character: int,
    variable_name: str,
    apply: bool = False,
) -> str:
    """Extract selected expression into a variable."""
    return "Not yet implemented"


async def inline_variable(file_path: str, line: int, character: int, apply: bool = False) -> str:
    """Inline a variable at the provided position."""
    return "Not yet implemented"


async def move_symbol(
    source_file: str,
    symbol_name: str,
    destination_file: str,
    apply: bool = False,
) -> str:
    """Move a symbol from one file to another."""
    return "Not yet implemented"
