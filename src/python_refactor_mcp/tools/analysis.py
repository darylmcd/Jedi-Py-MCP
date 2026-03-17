"""Analysis tools orchestrating Pyright and Jedi backends."""

from __future__ import annotations

from typing import Protocol

from python_refactor_mcp.models import Diagnostic, Location, ReferenceResult, TypeInfo

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


class _JediAnalysisBackend(Protocol):
    """Protocol describing Jedi analysis methods used by this module."""

    async def get_references(self, file_path: str, line: int, character: int) -> list[Location]:
        """Return references for a position."""
        ...

    async def infer_type(self, file_path: str, line: int, character: int) -> TypeInfo | None:
        """Return inferred type information for a position."""
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
        jedi_references = await jedi.get_references(file_path, line, character)
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

    jedi_references = await jedi.get_references(file_path, line, character)
    for location in jedi_references:
        key = _location_key(location)
        if key not in merged:
            source = "combined"
            merged[key] = location

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

    jedi_type = await jedi.infer_type(file_path, line, character)
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
