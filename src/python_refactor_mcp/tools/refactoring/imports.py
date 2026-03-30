"""Import-related refactoring tools: star expansion, relative-to-absolute, etc."""

from __future__ import annotations

from python_refactor_mcp.models import ImportSuggestion, RefactorResult

from .helpers import (
    PyrightRefactoringBackend,
    RopeRefactoringBackend,
    post_apply_diagnostics,
)


async def expand_star_imports(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    apply: bool = False,
) -> RefactorResult:
    """Replace ``from x import *`` with explicit named imports."""
    result = await rope.expand_star_imports(file_path, apply)
    return await post_apply_diagnostics(pyright, result)


async def relatives_to_absolutes(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    apply: bool = False,
) -> RefactorResult:
    """Convert all relative imports to absolute imports."""
    result = await rope.relatives_to_absolutes(file_path, apply)
    return await post_apply_diagnostics(pyright, result)


async def froms_to_imports(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    apply: bool = False,
) -> RefactorResult:
    """Convert ``from module import name`` to ``import module`` style."""
    result = await rope.froms_to_imports(file_path, apply)
    return await post_apply_diagnostics(pyright, result)


async def handle_long_imports(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    apply: bool = False,
) -> RefactorResult:
    """Break long import lines per project preferences."""
    result = await rope.handle_long_imports(file_path, apply)
    return await post_apply_diagnostics(pyright, result)


async def autoimport_search(
    rope: RopeRefactoringBackend,
    name: str,
) -> list[ImportSuggestion]:
    """Search for importable names using rope's AutoImport SQLite cache."""
    results = await rope.autoimport_search(name)
    return [
        ImportSuggestion(
            symbol=entry_name,
            module=module,
            import_statement=f"from {module} import {entry_name}",
        )
        for entry_name, module in results
    ]
