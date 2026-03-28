"""Reference-finding tools."""

from __future__ import annotations

import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

from python_refactor_mcp.models import (
    Location,
    ReferenceResult,
)
from python_refactor_mcp.tools.analysis._protocols import (
    JediAnalysisBackend as _JediAnalysisBackend,
)
from python_refactor_mcp.tools.analysis._protocols import (
    PyrightAnalysisBackend as _PyrightAnalysisBackend,
)
from python_refactor_mcp.util.shared import apply_limit
from python_refactor_mcp.util.shared import location_key as _location_key

_apply_limit = apply_limit


def _add_context_lines(locations: list[Location]) -> list[Location]:
    """Attach single-line source context to locations when files are readable."""
    enriched: list[Location] = []
    cache: dict[str, list[str]] = {}
    for location in locations:
        file_path = location.file_path
        line = location.range.start.line
        if file_path not in cache:
            try:
                cache[file_path] = Path(file_path).read_text(encoding="utf-8").splitlines()
            except Exception:
                _LOGGER.debug("failed to read file for context lines: %s", file_path, exc_info=True)
                cache[file_path] = []
        lines = cache[file_path]
        context: str | None = None
        if 0 <= line < len(lines):
            context = lines[line].rstrip("\r\n")
        enriched.append(location.model_copy(update={"context": context}))
    return enriched


async def find_references(
    pyright: _PyrightAnalysisBackend,
    jedi: _JediAnalysisBackend,
    file_path: str,
    line: int,
    character: int,
    include_declaration: bool = True,
    include_context: bool = False,
    limit: int | None = None,
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
            _LOGGER.debug("jedi reference fallback failed for %s:%d:%d", file_path, line, character, exc_info=True)
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
        final_refs = deduped_jedi
        if include_context:
            final_refs = _add_context_lines(final_refs)
        total_count = len(final_refs)
        final_refs, truncated = _apply_limit(final_refs, limit)
        return ReferenceResult(
            symbol=f"{file_path}:{line}:{character}",
            definition=None,
            references=final_refs,
            total_count=total_count,
            source="jedi",
            truncated=truncated,
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
        _LOGGER.debug("jedi reference enrichment failed for %s:%d:%d", file_path, line, character, exc_info=True)

    deduped = sorted(merged.values(), key=_location_key)
    if include_context:
        deduped = _add_context_lines(deduped)
    total_count = len(deduped)
    deduped, truncated = _apply_limit(deduped, limit)
    return ReferenceResult(
        symbol=f"{file_path}:{line}:{character}",
        definition=None,
        references=deduped,
        total_count=total_count,
        source=source,
        truncated=truncated,
    )
