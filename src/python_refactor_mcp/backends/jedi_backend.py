"""Jedi backend implementation for analysis fallbacks and symbol search."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path

import jedi  # type: ignore[import-untyped]

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import JediError
from python_refactor_mcp.models import (
    CompletionItem,
    DocumentationEntry,
    DocumentationResult,
    EnvironmentInfo,
    ImportSuggestion,
    InferredType,
    Location,
    NameEntry,
    ParameterInfo,
    ScopeContext,
    SignatureInfo,
    SymbolInfo,
    SyntaxErrorItem,
    TypeHintResult,
    TypeInfo,
)

_LOGGER = logging.getLogger(__name__)

_DEFAULT_JEDI_TIMEOUT = 10.0


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
        timeout_env = os.getenv("JEDI_OPERATION_TIMEOUT_SECONDS", "")
        try:
            self._timeout = max(float(timeout_env), 1.0) if timeout_env else _DEFAULT_JEDI_TIMEOUT
        except ValueError:
            self._timeout = _DEFAULT_JEDI_TIMEOUT

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
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
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
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
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
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
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
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi search_names returned %d suggestions for %s", len(result), symbol)
            return result
        except Exception as exc:
            raise JediError(f"Jedi search_names failed for symbol {symbol}") from exc

    async def search_symbols(self, query: str) -> list[SymbolInfo]:
        """Search project symbols by name using Jedi project search."""

        def _work() -> list[SymbolInfo]:
            project = self._require_project()
            names = project.search(query, all_scopes=True)
            symbols: list[SymbolInfo] = []
            seen: set[tuple[str, str, int, int, str]] = set()
            for name in names:
                location = _name_to_location(name)
                if location is None:
                    continue

                symbol_name = getattr(name, "name", "")
                if not isinstance(symbol_name, str) or not symbol_name:
                    continue

                kind_value = getattr(name, "type", "variable")
                kind = kind_value if isinstance(kind_value, str) and kind_value else "variable"
                module_name = getattr(name, "module_name", None)
                container = module_name if isinstance(module_name, str) and module_name else None
                key = (
                    symbol_name,
                    location.file_path,
                    location.range.start.line,
                    location.range.start.character,
                    container or "",
                )
                if key in seen:
                    continue
                seen.add(key)
                symbols.append(
                    SymbolInfo(
                        name=symbol_name,
                        kind=kind,
                        file_path=location.file_path,
                        range=location.range,
                        container=container,
                    )
                )
            return symbols

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi search_symbols returned %d results for %s", len(result), query)
            return result
        except Exception as exc:
            raise JediError(f"Jedi search_symbols failed for query {query}") from exc

    async def get_signatures(self, file_path: str, line: int, character: int) -> SignatureInfo | None:
        """Return call signatures for a source position using Jedi fallback APIs."""

        def _work() -> SignatureInfo | None:
            script = self._make_script(file_path)
            signatures = script.get_signatures(line=line + 1, column=character)
            if not signatures:
                return None

            signature = signatures[0]
            name_value = getattr(signature, "name", None)
            name = name_value if isinstance(name_value, str) and name_value else "call"

            params_raw = getattr(signature, "params", [])
            parameters: list[ParameterInfo] = []
            if isinstance(params_raw, list):
                for param in params_raw:
                    param_name_value = getattr(param, "name", None)
                    param_name = param_name_value if isinstance(param_name_value, str) else ""
                    if not param_name:
                        continue
                    parameters.append(ParameterInfo(label=param_name))

            label = name
            if parameters:
                label = f"{name}({', '.join(param.label for param in parameters)})"

            index = getattr(signature, "index", None)
            active_parameter = index if isinstance(index, int) else None

            return SignatureInfo(
                label=label,
                parameters=parameters,
                active_parameter=active_parameter,
                active_signature=0,
                documentation=None,
            )

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi get_signatures returned %s for %s", "value" if result else "none", file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi get_signatures failed for {file_path}:{line}:{character}") from exc

    async def get_help(
        self,
        file_path: str,
        line: int,
        character: int,
        source: str | None = None,
    ) -> DocumentationResult:
        """Return detailed help/doc entries for a source position."""

        def _work() -> DocumentationResult:
            script = self._make_script(file_path, source)
            names = script.help(line=line + 1, column=character)
            entries: list[DocumentationEntry] = []
            for name in names:
                module_path = _to_absolute_path(getattr(name, "module_path", None))
                kind_value = getattr(name, "type", None)
                kind = kind_value if isinstance(kind_value, str) else None
                full_doc = name.docstring(raw=True)
                signatures: list[str] = []
                signatures_raw = getattr(name, "get_signatures", None)
                if callable(signatures_raw):
                    try:
                        signatures_value = signatures_raw()
                        if not isinstance(signatures_value, list):
                            signatures_value = []
                        for signature in signatures_value:
                            signature_name = getattr(signature, "name", None)
                            params = getattr(signature, "params", [])
                            param_names: list[str] = []
                            if isinstance(params, list):
                                for param in params:
                                    param_name = getattr(param, "name", None)
                                    if isinstance(param_name, str) and param_name:
                                        param_names.append(param_name)
                            if isinstance(signature_name, str) and signature_name:
                                signatures.append(f"{signature_name}({', '.join(param_names)})")
                    except Exception:
                        pass

                entry_name = getattr(name, "name", "")
                entries.append(
                    DocumentationEntry(
                        name=entry_name if isinstance(entry_name, str) else "",
                        module_path=module_path,
                        kind=kind,
                        full_doc=full_doc or None,
                        signatures=signatures,
                    )
                )

            return DocumentationResult(
                file_path=str(Path(file_path).resolve()),
                line=line,
                character=character,
                entries=entries,
            )

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi get_help returned %d entries for %s", len(result.entries), file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi get_help failed for {file_path}:{line}:{character}") from exc

    async def deep_infer(self, file_path: str, line: int, character: int) -> list[InferredType]:
        """Follow imports and assignments to resolve final types via ``Script.infer()``."""

        def _work() -> list[InferredType]:
            script = self._make_script(file_path)
            names = script.infer(line=line + 1, column=character)
            results: list[InferredType] = []
            for name in names:
                entry_name = getattr(name, "name", "")
                if not isinstance(entry_name, str):
                    entry_name = ""
                full_name = getattr(name, "full_name", None)
                full_name = full_name if isinstance(full_name, str) else None
                type_string = str(getattr(name, "type", "unknown"))
                module_path = _to_absolute_path(getattr(name, "module_path", None))
                description = getattr(name, "description", None)
                description = description if isinstance(description, str) else None
                results.append(InferredType(
                    name=entry_name,
                    full_name=full_name,
                    type_string=type_string,
                    module_path=module_path,
                    line=_jedi_start_line(name),
                    character=_jedi_start_character(name),
                    description=description,
                ))
            return results

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi deep_infer returned %d types for %s", len(result), file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi deep_infer failed for {file_path}:{line}:{character}") from exc

    async def get_type_hint(self, file_path: str, line: int, character: int) -> list[TypeHintResult]:
        """Return ready-to-use type annotation strings via ``Name.get_type_hint()``."""

        def _work() -> list[TypeHintResult]:
            script = self._make_script(file_path)
            names = script.infer(line=line + 1, column=character)
            results: list[TypeHintResult] = []
            for name in names:
                entry_name = getattr(name, "name", "")
                if not isinstance(entry_name, str):
                    entry_name = ""
                full_name = getattr(name, "full_name", None)
                full_name = full_name if isinstance(full_name, str) else None
                hint: str | None = None
                get_type_hint_fn = getattr(name, "get_type_hint", None)
                if callable(get_type_hint_fn):
                    try:
                        raw_hint = get_type_hint_fn()
                        hint = raw_hint if isinstance(raw_hint, str) and raw_hint else None
                    except Exception:
                        pass
                results.append(TypeHintResult(
                    name=entry_name,
                    type_hint=hint,
                    full_name=full_name,
                ))
            return results

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi get_type_hint returned %d results for %s", len(result), file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi get_type_hint failed for {file_path}:{line}:{character}") from exc

    async def get_syntax_errors(self, file_path: str) -> list[SyntaxErrorItem]:
        """Detect syntax errors via Jedi's parser."""

        def _work() -> list[SyntaxErrorItem]:
            script = self._make_script(file_path)
            errors = script.get_syntax_errors()
            results: list[SyntaxErrorItem] = []
            for err in errors:
                msg = getattr(err, "message", "syntax error")
                if not isinstance(msg, str):
                    msg = "syntax error"
                line_val = getattr(err, "line", 1)
                col_val = getattr(err, "column", 0)
                until_line = getattr(err, "until_line", None)
                until_col = getattr(err, "until_column", None)
                results.append(SyntaxErrorItem(
                    file_path=str(Path(file_path).resolve()),
                    message=msg,
                    line=max((line_val if isinstance(line_val, int) else 1) - 1, 0),
                    character=max(col_val if isinstance(col_val, int) else 0, 0),
                    until_line=max(until_line - 1, 0) if isinstance(until_line, int) else None,
                    until_character=max(until_col, 0) if isinstance(until_col, int) else None,
                ))
            return results

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi get_syntax_errors returned %d errors for %s", len(result), file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi get_syntax_errors failed for {file_path}") from exc

    async def get_context(self, file_path: str, line: int, character: int) -> ScopeContext | None:
        """Return the enclosing function/class/module scope at a position."""

        def _work() -> ScopeContext | None:
            script = self._make_script(file_path)
            ctx = script.get_context(line=line + 1, column=character)
            if ctx is None:
                return None
            name = getattr(ctx, "name", "")
            if not isinstance(name, str):
                name = ""
            kind = str(getattr(ctx, "type", "module"))
            full_name = getattr(ctx, "full_name", None)
            full_name = full_name if isinstance(full_name, str) else None
            return ScopeContext(
                name=name,
                kind=kind,
                file_path=str(Path(file_path).resolve()),
                line=_jedi_start_line(ctx),
                character=_jedi_start_character(ctx),
                full_name=full_name,
            )

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi get_context returned %s for %s", result.kind if result else "none", file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi get_context failed for {file_path}:{line}:{character}") from exc

    async def get_names(
        self, file_path: str, all_scopes: bool = True, references: bool = False,
    ) -> list[NameEntry]:
        """List all defined names in a file, optionally including nested scopes."""

        def _work() -> list[NameEntry]:
            script = self._make_script(file_path)
            names = script.get_names(all_scopes=all_scopes, references=references)
            results: list[NameEntry] = []
            for name in names:
                entry_name = getattr(name, "name", "")
                if not isinstance(entry_name, str) or not entry_name:
                    continue
                kind = str(getattr(name, "type", "statement"))
                full_name = getattr(name, "full_name", None)
                full_name = full_name if isinstance(full_name, str) else None
                description = getattr(name, "description", None)
                description = description if isinstance(description, str) else None
                module_path = _to_absolute_path(getattr(name, "module_path", None))
                results.append(NameEntry(
                    name=entry_name,
                    kind=kind,
                    file_path=module_path,
                    line=_jedi_start_line(name),
                    character=_jedi_start_character(name),
                    full_name=full_name,
                    description=description,
                ))
            return results

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi get_names returned %d names for %s", len(result), file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi get_names failed for {file_path}") from exc

    async def get_completions(
        self, file_path: str, line: int, character: int, fuzzy: bool = False,
    ) -> list[CompletionItem]:
        """Return fuzzy completion candidates for a source position."""

        def _work() -> list[CompletionItem]:
            script = self._make_script(file_path)
            completions = script.complete(line=line + 1, column=character, fuzzy=fuzzy)
            items: list[CompletionItem] = []
            for c in completions:
                name = getattr(c, "name", "")
                if not isinstance(name, str) or not name:
                    continue
                kind_value = getattr(c, "type", "unknown")
                kind = kind_value if isinstance(kind_value, str) else "unknown"
                description = getattr(c, "description", None)
                detail = description if isinstance(description, str) else None
                doc: str | None = None
                try:
                    raw_doc = c.docstring()
                    doc = raw_doc if isinstance(raw_doc, str) and raw_doc else None
                except Exception:
                    pass
                items.append(
                    CompletionItem(
                        label=name,
                        kind=kind,
                        detail=detail,
                        insert_text=name,
                        documentation=doc,
                    )
                )
            return items

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi get_completions returned %d items for %s", len(result), file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi get_completions failed for {file_path}:{line}:{character}") from exc

    get_keyword_help = get_help

    async def get_sub_definitions(
        self, file_path: str, line: int, character: int,
    ) -> list[NameEntry]:
        """Return sub-definitions (defined names) of the name at a position."""

        def _work() -> list[NameEntry]:
            script = self._make_script(file_path)
            names = script.goto(line=line + 1, column=character)
            if not names:
                return []
            first = names[0]
            defined_names_fn = getattr(first, "defined_names", None)
            if not callable(defined_names_fn):
                return []
            sub_names = defined_names_fn()
            results: list[NameEntry] = []
            for name in sub_names:  # type: ignore[union-attr]
                entry_name = getattr(name, "name", "")
                if not isinstance(entry_name, str) or not entry_name:
                    continue
                kind = str(getattr(name, "type", "statement"))
                full_name = getattr(name, "full_name", None)
                full_name = full_name if isinstance(full_name, str) else None
                description = getattr(name, "description", None)
                description = description if isinstance(description, str) else None
                module_path = _to_absolute_path(getattr(name, "module_path", None))
                results.append(NameEntry(
                    name=entry_name,
                    kind=kind,
                    file_path=module_path,
                    line=_jedi_start_line(name),
                    character=_jedi_start_character(name),
                    full_name=full_name,
                    description=description,
                ))
            return results

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi get_sub_definitions returned %d names for %s", len(result), file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi get_sub_definitions failed for {file_path}:{line}:{character}") from exc

    async def simulate_execute(
        self, file_path: str, line: int, character: int,
    ) -> list[TypeInfo]:
        """Simulate calling a callable at the given position and return result types."""

        def _work() -> list[TypeInfo]:
            script = self._make_script(file_path)
            names = script.goto(line=line + 1, column=character)
            if not names:
                return []
            first = names[0]
            execute_fn = getattr(first, "execute", None)
            if not callable(execute_fn):
                return []
            executed = execute_fn()
            results: list[TypeInfo] = []
            for name in executed:  # type: ignore[union-attr]
                entry_name = getattr(name, "name", "")
                if not isinstance(entry_name, str):
                    entry_name = ""
                full_name = getattr(name, "full_name", None)
                type_string = (
                    full_name if isinstance(full_name, str) and full_name
                    else str(getattr(name, "type", "unknown"))
                )
                doc: str | None = None
                try:
                    raw_doc = name.docstring(raw=True)
                    doc = raw_doc if isinstance(raw_doc, str) and raw_doc else None
                except Exception:
                    pass
                expression = str(Path(file_path).resolve()) + f":{line}:{character}"
                results.append(TypeInfo(
                    expression=expression,
                    type_string=type_string,
                    documentation=doc,
                    source="jedi",
                ))
            return results

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi simulate_execute returned %d types for %s", len(result), file_path)
            return result
        except Exception as exc:
            raise JediError(f"Jedi simulate_execute failed for {file_path}:{line}:{character}") from exc

    async def list_environments(self) -> list[EnvironmentInfo]:
        """List available Python environments discovered by Jedi."""

        def _work() -> list[EnvironmentInfo]:
            envs: list[EnvironmentInfo] = []
            seen_paths: set[str] = set()

            for env in jedi.find_virtualenvs():
                env_path = str(getattr(env, "executable", getattr(env, "path", "")))
                if not env_path or env_path in seen_paths:
                    continue
                seen_paths.add(env_path)
                version_info = getattr(env, "version_info", None)
                version = None
                if version_info is not None:
                    with contextlib.suppress(Exception):
                        version = ".".join(str(v) for v in version_info[:3])
                envs.append(EnvironmentInfo(
                    path=env_path,
                    python_version=version or "unknown",
                    is_virtualenv=True,
                ))

            for env in jedi.find_system_environments():
                env_path = str(getattr(env, "executable", getattr(env, "path", "")))
                if not env_path or env_path in seen_paths:
                    continue
                seen_paths.add(env_path)
                version_info = getattr(env, "version_info", None)
                version = None
                if version_info is not None:
                    with contextlib.suppress(Exception):
                        version = ".".join(str(v) for v in version_info[:3])
                envs.append(EnvironmentInfo(
                    path=env_path,
                    python_version=version or "unknown",
                    is_virtualenv=False,
                ))

            return envs

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi list_environments returned %d environments", len(result))
            return result
        except Exception as exc:
            raise JediError("Jedi list_environments failed") from exc

    async def project_search(self, query: str, complete: bool = False) -> list[SymbolInfo]:
        """Search project symbols by name, optionally using completion-style search."""

        def _work() -> list[SymbolInfo]:
            project = self._require_project()
            names = project.complete_search(query) if complete else project.search(query, all_scopes=True)
            symbols: list[SymbolInfo] = []
            seen: set[tuple[str, str, int, int, str]] = set()
            for name in names:
                location = _name_to_location(name)
                if location is None:
                    continue

                symbol_name = getattr(name, "name", "")
                if not isinstance(symbol_name, str) or not symbol_name:
                    continue

                kind_value = getattr(name, "type", "variable")
                kind = kind_value if isinstance(kind_value, str) and kind_value else "variable"
                module_name = getattr(name, "module_name", None)
                container = module_name if isinstance(module_name, str) and module_name else None
                key = (
                    symbol_name,
                    location.file_path,
                    location.range.start.line,
                    location.range.start.character,
                    container or "",
                )
                if key in seen:
                    continue
                seen.add(key)
                symbols.append(
                    SymbolInfo(
                        name=symbol_name,
                        kind=kind,
                        file_path=location.file_path,
                        range=location.range,
                        container=container,
                    )
                )
            return symbols

        try:
            result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("Jedi project_search returned %d results for %s", len(result), query)
            return result
        except Exception as exc:
            raise JediError(f"Jedi project_search failed for query {query}") from exc
