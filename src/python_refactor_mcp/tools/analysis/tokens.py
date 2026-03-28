"""Document highlight, inlay hint, and semantic token tools."""

from __future__ import annotations

from python_refactor_mcp.models import (
    DocumentHighlight,
    InlayHint,
    SemanticToken,
)
from python_refactor_mcp.tools.analysis._protocols import (
    PyrightAnalysisBackend as _PyrightAnalysisBackend,
)


async def get_document_highlights(
    pyright: _PyrightAnalysisBackend,
    file_path: str,
    line: int,
    character: int,
) -> list[DocumentHighlight]:
    """Get in-file read/write highlights for a symbol position."""
    highlights = await pyright.get_document_highlights(file_path, line, character)
    return sorted(
        highlights,
        key=lambda item: (
            item.range.start.line,
            item.range.start.character,
            item.range.end.line,
            item.range.end.character,
            item.kind,
        ),
    )


async def get_inlay_hints(
    pyright: _PyrightAnalysisBackend,
    file_path: str,
    start_line: int,
    start_character: int,
    end_line: int,
    end_character: int,
) -> list[InlayHint]:
    """Get inlay hints for the supplied source range."""
    hints = await pyright.get_inlay_hints(
        file_path,
        start_line,
        start_character,
        end_line,
        end_character,
    )
    return sorted(hints, key=lambda item: (item.position.line, item.position.character, item.label))


async def get_semantic_tokens(
    pyright: _PyrightAnalysisBackend,
    file_path: str,
) -> list[SemanticToken]:
    """Get semantic tokens for a file and return deterministic ordering."""
    tokens = await pyright.get_semantic_tokens(file_path)
    return sorted(
        tokens,
        key=lambda item: (
            item.range.start.line,
            item.range.start.character,
            item.token_type,
        ),
    )
