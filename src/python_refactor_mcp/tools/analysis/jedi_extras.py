"""Jedi-powered analysis tools: deep inference, type hints, syntax errors, context, names."""

from __future__ import annotations

from python_refactor_mcp.models import InferredType, NameEntry, ScopeContext, SyntaxErrorItem, TypeHintResult

from ._protocols import JediAnalysisBackend as _JediBackend


async def deep_type_inference(
    jedi: _JediBackend,
    file_path: str,
    line: int,
    character: int,
) -> list[InferredType]:
    """Follow imports and assignments to resolve final types at a position."""
    return await jedi.deep_infer(file_path, line, character)


async def get_type_hint_string(
    jedi: _JediBackend,
    file_path: str,
    line: int,
    character: int,
) -> list[TypeHintResult]:
    """Return ready-to-use type annotation strings for a symbol."""
    return await jedi.get_type_hint(file_path, line, character)


async def get_syntax_errors(
    jedi: _JediBackend,
    file_path: str,
) -> list[SyntaxErrorItem]:
    """Detect syntax errors via Jedi's parser."""
    return await jedi.get_syntax_errors(file_path)


async def get_context(
    jedi: _JediBackend,
    file_path: str,
    line: int,
    character: int,
) -> ScopeContext | None:
    """Return the enclosing function/class/module scope at a position."""
    return await jedi.get_context(file_path, line, character)


async def get_all_names(
    jedi: _JediBackend,
    file_path: str,
    all_scopes: bool = True,
    references: bool = False,
) -> list[NameEntry]:
    """List all defined names in a file with optional nested scopes."""
    return await jedi.get_names(file_path, all_scopes=all_scopes, references=references)
