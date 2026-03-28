"""Type information, hover, and documentation tools."""

from __future__ import annotations

from python_refactor_mcp.models import (
    DocumentationResult,
    TypeInfo,
)
from python_refactor_mcp.tools.analysis._protocols import (
    JediAnalysisBackend as _JediAnalysisBackend,
)
from python_refactor_mcp.tools.analysis._protocols import (
    PyrightAnalysisBackend as _PyrightAnalysisBackend,
)


def _is_unknown_type(type_info: TypeInfo | None) -> bool:
    """Return True when type info is missing or effectively unknown."""
    if type_info is None:
        return True

    lowered = type_info.type_string.strip().lower()
    return lowered in {"", "unknown", "any"} or " unknown" in lowered


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
        # pyright_type is guaranteed non-None here because _is_unknown_type(None) returns True.
        return pyright_type  # type: ignore[return-value]

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


async def get_documentation(
    jedi: _JediAnalysisBackend,
    file_path: str,
    line: int,
    character: int,
    source: str | None = None,
) -> DocumentationResult:
    """Get detailed symbol documentation/help using Jedi."""
    return await jedi.get_help(file_path, line, character, source)
