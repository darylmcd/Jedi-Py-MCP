"""Search tool placeholders for Stage 1."""

from __future__ import annotations


async def find_constructors(class_name: str, file_path: str | None = None) -> str:
    """Find constructor call sites for a class."""
    return "Not yet implemented"


async def structural_search(
    pattern: str,
    file_path: str | None = None,
    language: str = "python",
) -> str:
    """Run structural search across code using a pattern."""
    return "Not yet implemented"


async def dead_code_detection(file_path: str | None = None) -> str:
    """Detect dead code candidates in a file or project."""
    return "Not yet implemented"


async def suggest_imports(symbol: str, file_path: str) -> str:
    """Suggest imports for an unresolved symbol in context."""
    return "Not yet implemented"
