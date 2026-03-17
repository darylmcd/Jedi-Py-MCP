"""Jedi backend implementation for analysis fallbacks and symbol search."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import jedi  # type: ignore[import-untyped]

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import JediError
from python_refactor_mcp.models import ImportSuggestion, Location, TypeInfo

_LOGGER = logging.getLogger(__name__)


def _to_absolute_path(path: str | Path | None) -> str | None:
    """Return an absolute string path when path is present."""
    if path is None:
        return None
    return str(Path(path).resolve())


def _jedi_start_line(name: object) -> int:
    """Convert a Jedi line value into a 0-based start line."""
    line_value = getattr(name, "line", 1)
    if not isinstance(line_value, int):
        line_value = 1
    return max(line_value - 1, 0)


def _jedi_start_character(name: object) -> int:
    """Convert a Jedi column value into a 0-based start character."""
    column_value = getattr(name, "column", 0)
    if not isinstance(column_value, int):
        column_value = 0
    return max(column_value, 0)


def _name_to_location(name: object) -> Location | None:
    """Convert a Jedi Name into a Location model."""
    module_path = _to_absolute_path(getattr(name, "module_path", None))
    if module_path is None:
        return None

    start_line = _jedi_start_line(name)
    start_character = _jedi_start_character(name)
    end_line = start_line
    symbol_name = getattr(name, "name", "")
    if not isinstance(symbol_name, str):
        symbol_name = ""
    end_character = start_character + len(symbol_name)
    return Location.model_validate(
        {
            "file_path": module_path,
            "range": {
                "start": {"line": start_line, "character": start_character},
                "end": {"line": end_line, "character": end_character},
            },
        }
    )


class JediBackend:
    """Jedi analysis backend used as dynamic fallback for semantic tools."""

    def __init__(self, config: ServerConfig) -> None:
        """Initialize backend config and deferred project state."""
        self._config = config
        self._project: jedi.Project | None = None

    def initialize(self) -> None:
        """Create a Jedi project for the configured workspace root."""
        if self._config.venv_path is not None:
            self._project = jedi.Project(
                path=str(self._config.workspace_root),
                environment_path=str(self._config.venv_path),
            )
        else:
            self._project = jedi.Project(path=str(self._config.workspace_root))

    def _require_project(self) -> jedi.Project:
        """Return initialized Jedi project or raise a structured backend error."""
        if self._project is None:
            raise JediError("Jedi backend is not initialized.")
        return self._project

    def _make_script(self, file_path: str, source: str | None = None) -> jedi.Script:
        """Create a Jedi script in project context using disk or provided source."""
        project = self._require_project()
        absolute_path = str(Path(file_path).resolve())
        script_source = source
        if script_source is None:
            script_source = Path(absolute_path).read_text(encoding="utf-8")
        return jedi.Script(code=script_source, path=absolute_path, project=project)

    async def get_references(self, file_path: str, line: int, character: int) -> list[Location]:
        """Return references for a symbol position using Jedi lookup."""

        def _work() -> list[Location]:
            script = self._make_script(file_path)
            names = script.get_references(line=line + 1, column=character)
            locations: list[Location] = []
            for name in names:
                location = _name_to_location(name)
                if location is not None:
                    locations.append(location)
            return locations

        try:
            result = await asyncio.to_thread(_work)
            _LOGGER.debug("Jedi get_references resolved %d locations for %s", len(result), file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi get_references failed for {file_path}:{line}:{character}") from exc

    async def goto_definition(self, file_path: str, line: int, character: int) -> list[Location]:
        """Return definitions for a symbol position using Jedi goto."""

        def _work() -> list[Location]:
            script = self._make_script(file_path)
            names = script.goto(line=line + 1, column=character, follow_imports=True)
            locations: list[Location] = []
            for name in names:
                location = _name_to_location(name)
                if location is not None:
                    locations.append(location)
            return locations

        try:
            result = await asyncio.to_thread(_work)
            _LOGGER.debug("Jedi goto_definition resolved %d locations for %s", len(result), file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi goto_definition failed for {file_path}:{line}:{character}") from exc

    async def infer_type(self, file_path: str, line: int, character: int) -> TypeInfo | None:
        """Infer type information for a symbol position using Jedi inference."""

        def _work() -> TypeInfo | None:
            script = self._make_script(file_path)
            inferences = script.infer(line=line + 1, column=character)
            if not inferences:
                return None

            first = inferences[0]
            doc = first.docstring(raw=True)
            type_string = str(getattr(first, "type", "unknown"))
            full_name = getattr(first, "full_name", None)
            if isinstance(full_name, str) and full_name:
                type_string = full_name
            expression = str(Path(file_path).resolve()) + f":{line}:{character}"
            return TypeInfo(
                expression=expression,
                type_string=type_string,
                documentation=doc or None,
                source="jedi",
            )

        try:
            result = await asyncio.to_thread(_work)
            _LOGGER.debug("Jedi infer_type returned %s for %s", "value" if result else "none", file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi infer_type failed for {file_path}:{line}:{character}") from exc

    async def search_names(self, symbol: str) -> list[ImportSuggestion]:
        """Search project names and convert them into import suggestions."""

        def _work() -> list[ImportSuggestion]:
            project = self._require_project()
            names = project.search(symbol, all_scopes=True)
            suggestions: list[ImportSuggestion] = []
            seen: set[tuple[str, str]] = set()
            for name in names:
                if name.name != symbol:
                    continue
                module_name_value = getattr(name, "module_name", None)
                module_name = module_name_value if isinstance(module_name_value, str) else ""
                if not module_name:
                    module_path = _to_absolute_path(getattr(name, "module_path", None))
                    if module_path is None:
                        continue
                    module_name = Path(module_path).stem
                key = (symbol, module_name)
                if key in seen:
                    continue
                seen.add(key)
                suggestions.append(
                    ImportSuggestion(
                        symbol=symbol,
                        module=module_name,
                        import_statement=f"from {module_name} import {symbol}",
                    )
                )
            return suggestions

        try:
            result = await asyncio.to_thread(_work)
            _LOGGER.debug("Jedi search_names returned %d suggestions for %s", len(result), symbol)
            return result
        except Exception as exc:
            raise JediError(f"Jedi search_names failed for symbol {symbol}") from exc
