"""Protocol classes for analysis backend dependencies."""

from __future__ import annotations

from typing import Protocol

from python_refactor_mcp.models import (
    CompletionItem,
    Diagnostic,
    DocumentationResult,
    DocumentHighlight,
    InlayHint,
    Location,
    SemanticToken,
    SignatureInfo,
    TypeInfo,
)


class PyrightAnalysisBackend(Protocol):
    """Protocol describing Pyright analysis methods used by this module."""

    async def get_references(
        self,
        file_path: str,
        line: int,
        char: int,
        include_declaration: bool,
    ) -> list[Location]:
        """Return references for a position."""
        ...

    async def get_hover(self, file_path: str, line: int, char: int) -> TypeInfo | None:
        """Return hover-based type information for a position."""
        ...

    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]:
        """Return diagnostics for one file or the full workspace."""
        ...

    async def get_completions(self, file_path: str, line: int, char: int) -> list[CompletionItem]:
        """Return completion candidates for a source position."""
        ...

    async def get_signature_help(self, file_path: str, line: int, char: int) -> SignatureInfo | None:
        """Return signature help for a source position."""
        ...

    async def get_document_highlights(
        self,
        file_path: str,
        line: int,
        char: int,
    ) -> list[DocumentHighlight]:
        """Return in-file highlights for the symbol under cursor."""
        ...

    async def get_inlay_hints(
        self,
        file_path: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
    ) -> list[InlayHint]:
        """Return inlay hints for a source range."""
        ...

    async def get_semantic_tokens(self, file_path: str) -> list[SemanticToken]:
        """Return decoded semantic tokens for a full file."""
        ...


class JediAnalysisBackend(Protocol):
    """Protocol describing Jedi analysis methods used by this module."""

    async def get_references(self, file_path: str, line: int, character: int) -> list[Location]:
        """Return references for a position."""
        ...

    async def infer_type(self, file_path: str, line: int, character: int) -> TypeInfo | None:
        """Return inferred type information for a position."""
        ...

    async def get_signatures(self, file_path: str, line: int, character: int) -> SignatureInfo | None:
        """Return Jedi signature help for dynamic fallback scenarios."""
        ...

    async def get_help(
        self,
        file_path: str,
        line: int,
        character: int,
        source: str | None = None,
    ) -> DocumentationResult:
        """Return detailed help/doc entries for a source position."""
        ...
