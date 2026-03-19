"""Analysis tools orchestrating Pyright and Jedi backends."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    CompletionItem,
    Diagnostic,
    DiagnosticSummary,
    DocumentHighlight,
    InlayHint,
    Location,
    ReferenceResult,
    SemanticToken,
    SignatureInfo,
    TypeInfo,
)

_VALID_SEVERITIES = {"error", "warning", "information", "hint"}


class _PyrightAnalysisBackend(Protocol):
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


class _JediAnalysisBackend(Protocol):
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


def _is_unknown_type(type_info: TypeInfo | None) -> bool:
    """Return True when type info is missing or effectively unknown."""
    if type_info is None:
        return True

    lowered = type_info.type_string.strip().lower()
    return lowered in {"", "unknown", "any"} or " unknown" in lowered


def _location_key(location: Location) -> tuple[str, int, int, int, int]:
    """Build a stable key for location-like objects."""
    file_path = str(getattr(location, "file_path", ""))
    range_value = getattr(location, "range", None)
    start = getattr(range_value, "start", None)
    end = getattr(range_value, "end", None)
    start_line = int(getattr(start, "line", 0))
    start_character = int(getattr(start, "character", 0))
    end_line = int(getattr(end, "line", 0))
    end_character = int(getattr(end, "character", 0))
    return (file_path, start_line, start_character, end_line, end_character)


def _sort_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    """Return diagnostics sorted by file and source order position."""
    return sorted(
        diagnostics,
        key=lambda item: (
            item.file_path,
            item.range.start.line,
            item.range.start.character,
            item.range.end.line,
            item.range.end.character,
        ),
    )


async def find_references(
    pyright: _PyrightAnalysisBackend,
    jedi: _JediAnalysisBackend,
    file_path: str,
    line: int,
    character: int,
    include_declaration: bool = True,
) -> ReferenceResult:
    """Find symbol references via analysis backends."""
    pyright_references = await pyright.get_references(
        file_path,
        line,
        character,
        include_declaration,
    )

    if not pyright_references:
        try:
            jedi_references = await jedi.get_references(file_path, line, character)
        except Exception:
            return ReferenceResult(
                symbol=f"{file_path}:{line}:{character}",
                definition=None,
                references=[],
                total_count=0,
                source="pyright",
            )
        deduped_jedi = sorted(
            {
                _location_key(location): location
                for location in jedi_references
            }.values(),
            key=_location_key,
        )
        return ReferenceResult(
            symbol=f"{file_path}:{line}:{character}",
            definition=None,
            references=deduped_jedi,
            total_count=len(deduped_jedi),
            source="jedi",
        )

    merged = {
        _location_key(location): location
        for location in pyright_references
    }
    source = "pyright"

    try:
        jedi_references = await jedi.get_references(file_path, line, character)
        for location in jedi_references:
            key = _location_key(location)
            if key not in merged:
                source = "combined"
                merged[key] = location
    except Exception:
        # Keep the Pyright result if Jedi enrichment fails.
        pass

    deduped = sorted(merged.values(), key=_location_key)
    return ReferenceResult(
        symbol=f"{file_path}:{line}:{character}",
        definition=None,
        references=deduped,
        total_count=len(deduped),
        source=source,
    )


async def get_type_info(
    pyright: _PyrightAnalysisBackend,
    jedi: _JediAnalysisBackend,
    file_path: str,
    line: int,
    character: int,
) -> TypeInfo:
    """Get type information for a symbol position."""
    pyright_type = await pyright.get_hover(file_path, line, character)
    if not _is_unknown_type(pyright_type):
        if pyright_type is None:
            return TypeInfo(
                expression=f"{file_path}:{line}:{character}",
                type_string="Unknown",
                documentation=None,
                source="pyright",
            )
        return pyright_type

    try:
        jedi_type = await jedi.infer_type(file_path, line, character)
    except Exception:
        jedi_type = None
    if jedi_type is not None:
        return jedi_type

    if pyright_type is not None:
        return pyright_type

    return TypeInfo(
        expression=f"{file_path}:{line}:{character}",
        type_string="Unknown",
        documentation=None,
        source="combined",
    )


async def get_hover_info(
    pyright: _PyrightAnalysisBackend,
    jedi: _JediAnalysisBackend,
    file_path: str,
    line: int,
    character: int,
) -> TypeInfo:
    """Get hover-style symbol information with Jedi fallback for unknown results."""
    return await get_type_info(pyright, jedi, file_path, line, character)


async def get_completions(
    pyright: _PyrightAnalysisBackend,
    file_path: str,
    line: int,
    character: int,
) -> list[CompletionItem]:
    """Get code completion candidates from the primary analysis backend."""
    completions = await pyright.get_completions(file_path, line, character)
    return sorted(completions, key=lambda item: (item.label, item.kind, item.detail or ""))


async def get_signature_help(
    pyright: _PyrightAnalysisBackend,
    file_path: str,
    line: int,
    character: int,
) -> SignatureInfo | None:
    """Get function signature help for a call-site position."""
    return await pyright.get_signature_help(file_path, line, character)


async def get_call_signatures_fallback(
    jedi: _JediAnalysisBackend,
    file_path: str,
    line: int,
    character: int,
) -> SignatureInfo | None:
    """Get Jedi signature help as a fallback for dynamic call sites."""
    return await jedi.get_signatures(file_path, line, character)


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


async def get_diagnostics(
    pyright: _PyrightAnalysisBackend,
    file_path: str | None = None,
    severity_filter: str | None = None,
) -> list[Diagnostic]:
    """Get diagnostics for one file or the full project."""
    normalized_severity: str | None = None
    if severity_filter is not None:
        normalized_severity = severity_filter.strip().lower()
        if normalized_severity not in _VALID_SEVERITIES:
            valid = ", ".join(sorted(_VALID_SEVERITIES))
            raise ValueError(f"Invalid severity_filter '{severity_filter}'. Expected one of: {valid}")

    diagnostics = await pyright.get_diagnostics(file_path)
    if normalized_severity is not None:
        diagnostics = [
            diagnostic
            for diagnostic in diagnostics
            if diagnostic.severity.strip().lower() == normalized_severity
        ]

    return _sort_diagnostics(diagnostics)


async def get_workspace_diagnostics(
    pyright: _PyrightAnalysisBackend,
    config: ServerConfig,
) -> list[DiagnosticSummary]:
    """Aggregate workspace diagnostics into one summary per file."""
    diagnostics: list[Diagnostic] = []
    for path in sorted(config.workspace_root.rglob("*.py")):
        if not path.is_file():
            continue
        diagnostics.extend(await pyright.get_diagnostics(str(Path(path).resolve())))
    by_file: dict[str, dict[str, int]] = {}

    for diagnostic in diagnostics:
        counts = by_file.setdefault(
            diagnostic.file_path,
            {
                "error": 0,
                "warning": 0,
                "information": 0,
                "hint": 0,
            },
        )
        severity = diagnostic.severity.strip().lower()
        if severity not in counts:
            severity = "information"
        counts[severity] += 1

    summaries = [
        DiagnosticSummary(
            file_path=file_path,
            error_count=counts["error"],
            warning_count=counts["warning"],
            information_count=counts["information"],
            hint_count=counts["hint"],
            total_count=sum(counts.values()),
        )
        for file_path, counts in by_file.items()
    ]
    return sorted(summaries, key=lambda item: item.file_path)
