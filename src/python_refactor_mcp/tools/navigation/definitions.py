"""Definition, implementation, declaration, and type-definition navigation tools."""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

from python_refactor_mcp.models import Location
from python_refactor_mcp.util.shared import location_key as _location_key

from ._protocols import _JediNavigationBackend, _PyrightNavigationBackend


async def goto_definition(
    pyright: _PyrightNavigationBackend,
    jedi: _JediNavigationBackend,
    file_path: str,
    line: int,
    character: int,
) -> list[Location]:
    """Navigate to symbol definitions from a source position."""
    pyright_locations = await pyright.get_definition(file_path, line, character)
    if pyright_locations:
        deduped = {
            _location_key(location): location
            for location in pyright_locations
        }
        return sorted(deduped.values(), key=_location_key)

    try:
        jedi_locations = await jedi.goto_definition(file_path, line, character)
    except Exception:
        _LOGGER.debug("jedi goto_definition fallback failed for %s:%d:%d", file_path, line, character, exc_info=True)
        return []
    deduped_jedi = {
        _location_key(location): location
        for location in jedi_locations
    }
    return sorted(deduped_jedi.values(), key=_location_key)


async def find_implementations(
    pyright: _PyrightNavigationBackend,
    file_path: str,
    line: int,
    character: int,
) -> list[Location]:
    """Find implementation locations for the symbol at the provided position."""
    implementations = await pyright.get_implementation(file_path, line, character)
    deduped = {
        _location_key(location): location
        for location in implementations
    }
    return sorted(deduped.values(), key=_location_key)


async def get_declaration(
    pyright: _PyrightNavigationBackend,
    file_path: str,
    line: int,
    character: int,
) -> list[Location]:
    """Navigate to symbol declarations from a source position."""
    declarations = await pyright.get_declaration(file_path, line, character)
    deduped = {
        _location_key(location): location
        for location in declarations
    }
    return sorted(deduped.values(), key=_location_key)


async def get_type_definition(
    pyright: _PyrightNavigationBackend,
    file_path: str,
    line: int,
    character: int,
) -> list[Location]:
    """Navigate to symbol type definitions from a source position."""
    definitions = await pyright.get_type_definition(file_path, line, character)
    deduped = {
        _location_key(location): location
        for location in definitions
    }
    return sorted(deduped.values(), key=_location_key)
