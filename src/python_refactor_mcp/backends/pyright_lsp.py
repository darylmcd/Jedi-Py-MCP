"""Pyright language server backend over async JSON-RPC/LSP transport."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import PyrightError
from python_refactor_mcp.models import (
    CallHierarchyItem,
    CompletionItem,
    Diagnostic,
    DocumentHighlight,
    FoldingRange,
    InlayHint,
    Location,
    ParameterInfo,
    Position,
    PrepareRenameResult,
    Range,
    SelectionRangeResult,
    SemanticToken,
    SignatureInfo,
    SymbolInfo,
    SymbolOutlineItem,
    TypeHierarchyItem,
    TypeInfo,
)
from python_refactor_mcp.util.lsp_client import JSONDict, JSONValue, LSPClient
from python_refactor_mcp.util.lsp_converters import (
    DOCUMENT_HIGHLIGHT_KIND,
    SEMANTIC_TOKEN_MODIFIERS,
    SEMANTIC_TOKEN_TYPES,
    SYMBOL_KIND,
    as_int,
    as_str,
    call_hierarchy_item_to_lsp,
    call_hierarchy_item_to_model,
    convert_publish_diagnostics,
    definition_entry_to_locations,
    extract_hover_text,
    is_unhandled_method_error,
    model_position,
    model_range,
    severity_from_string,
    type_hierarchy_item_to_lsp,
    type_hierarchy_item_to_model,
)
from python_refactor_mcp.util.paths import normalize_path, path_to_uri, uri_to_path
from python_refactor_mcp.util.timing import timed

_LOGGER = logging.getLogger(__name__)


def _convert_document_symbol(entry: JSONDict, fallback_path: str) -> SymbolOutlineItem | None:
    """Convert a single LSP DocumentSymbol or SymbolInformation to a model item."""
    name = as_str(entry.get("name"), "")
    if not name:
        return None

    kind_value = as_int(entry.get("kind", 13), 13)
    range_value = entry.get("range")
    selection_value = entry.get("selectionRange")

    if not isinstance(range_value, dict):
        location_value = entry.get("location")
        if isinstance(location_value, dict):
            range_value = location_value.get("range")
            uri_value = location_value.get("uri")
            if isinstance(uri_value, str):
                fallback_path = uri_to_path(uri_value)

    if not isinstance(range_value, dict):
        return None
    if not isinstance(selection_value, dict):
        selection_value = range_value

    file_uri = entry.get("uri")
    resolved_path = uri_to_path(file_uri) if isinstance(file_uri, str) else fallback_path

    children: list[SymbolOutlineItem] = []
    raw_children = entry.get("children")
    if isinstance(raw_children, list):
        for child in raw_children:
            if not isinstance(child, dict):
                continue
            converted_child = _convert_document_symbol(child, resolved_path)
            if converted_child is not None:
                children.append(converted_child)

    container = entry.get("containerName")
    return SymbolOutlineItem(
        name=name,
        kind=SYMBOL_KIND.get(kind_value, "symbol"),
        file_path=resolved_path,
        range=model_range(range_value),
        selection_range=model_range(selection_value),
        detail=as_str(entry.get("detail"), "") or None,
        container=container if isinstance(container, str) else None,
        children=children,
    )


def _reconstruct_symbol_hierarchy(symbols: list[SymbolOutlineItem]) -> list[SymbolOutlineItem]:
    """Reconstruct parent/child hierarchy from flat SymbolInformation format."""
    has_containers = any(s.container for s in symbols)
    has_children = any(s.children for s in symbols)
    if not has_containers or has_children:
        return symbols

    by_name: dict[str, list[SymbolOutlineItem]] = {}
    for sym in symbols:
        by_name.setdefault(sym.name, []).append(sym)

    roots: list[SymbolOutlineItem] = []
    for sym in symbols:
        if sym.container and sym.container in by_name:
            parent = by_name[sym.container][0]
            if parent is not sym:
                parent.children.append(sym)
                continue
        roots.append(sym)
    return roots


class PyrightLSPClient:
    """Pyright backend that wraps language-server calls with model conversion."""

    def __init__(self, config: ServerConfig) -> None:
        """Initialize the Pyright backend with server config."""
        self._config = config
        self._client = self._make_client()
        timeout_env = os.getenv("PYRIGHT_REQUEST_TIMEOUT_SECONDS", "5")
        try:
            self._request_timeout_seconds = max(float(timeout_env), 1.0)
        except ValueError:
            self._request_timeout_seconds = 5.0
        self._open_files: set[str] = set()
        self._file_versions: dict[str, int] = {}
        self._content_hashes: dict[str, str] = {}
        self._diagnostics: dict[str, list[Diagnostic]] = {}
        self._diagnostics_events: dict[str, asyncio.Event] = {}
        self._startup_command: list[str] | None = None
        self._restarting = False

    # ── LSP transport ─────────────────────────────────────────────────

    async def _request(self, method: str, params: dict[str, JSONValue]) -> JSONDict:
        """Send an LSP request with a bounded timeout and auto-restart on crash."""
        await self._ensure_healthy()
        try:
            async with timed(_LOGGER, f"pyright.{method}"):
                return await asyncio.wait_for(
                    self._client.send_request(method, params),
                    timeout=self._request_timeout_seconds,
                )
        except TimeoutError as exc:
            raise PyrightError(
                f"{method} request timed out after {self._request_timeout_seconds:.1f}s"
            ) from exc
        except PyrightError:
            if self._client.is_alive():
                raise
            # Process died during request — attempt single restart and retry.
            _LOGGER.warning("Pyright process died during %s request, attempting restart", method)
            await self._restart()
            return await asyncio.wait_for(
                self._client.send_request(method, params),
                timeout=self._request_timeout_seconds,
            )

    async def _ensure_healthy(self) -> None:
        """Check if Pyright is alive and restart if it has crashed."""
        if self._restarting or self._client.is_alive():
            return
        _LOGGER.warning("Pyright process detected as dead, attempting restart")
        await self._restart()

    async def _restart(self) -> None:
        """Restart the Pyright process using the stored startup command."""
        if self._startup_command is None:
            raise PyrightError("Cannot restart Pyright: no startup command recorded")
        if self._restarting:
            return
        self._restarting = True
        try:
            await self._client.shutdown()
            # Clear stale state.
            self._open_files.clear()
            self._file_versions.clear()
            self._diagnostics.clear()
            self._diagnostics_events.clear()
            # Create fresh client and re-run startup.
            self._client = self._make_client()
            initialize_params = self._build_initialize_params()
            await self._client.start(self._startup_command)
            response = await asyncio.wait_for(
                self._client.send_request("initialize", initialize_params),
                timeout=15,
            )
            if "error" in response:
                raise PyrightError(f"Pyright re-initialize failed: {response['error']}")
            await self._client.send_notification("initialized", {})
            settings: dict[str, JSONValue] = {
                "python": {
                    "pythonPath": str(self._config.python_executable),
                    "analysis": {
                        "diagnosticMode": "openFilesOnly",
                        "autoSearchPaths": True,
                        "useLibraryCodeForTypes": True,
                    },
                }
            }
            await self._client.send_notification(
                "workspace/didChangeConfiguration", {"settings": settings},
            )
            _LOGGER.info("Pyright process restarted successfully")
        finally:
            self._restarting = False

    def _make_client(self) -> LSPClient:
        """Create and configure a fresh LSP transport client."""
        client = LSPClient()
        client.register_notification_handler(
            "textDocument/publishDiagnostics",
            self._handle_publish_diagnostics,
        )
        return client

    def _candidate_commands(self) -> list[list[str]]:
        """Build candidate commands to launch pyright-langserver robustly."""
        candidates: list[list[str]] = []

        configured = self._config.pyright_executable.strip()
        module_python_candidates: list[str] = [str(self._config.python_executable)]

        configured_path = Path(configured)
        if configured and configured_path.is_absolute():
            launcher_dir = configured_path.parent
            inferred_python = launcher_dir / ("python.exe" if os.name == "nt" else "python")
            if inferred_python.exists():
                module_python_candidates.insert(0, str(inferred_python))

        for python_command in module_python_candidates:
            candidates.append([python_command, "-m", "pyright.langserver", "--stdio"])

        if configured:
            configured_lower = configured.lower()
            if os.name == "nt" and configured_lower.endswith(".cmd"):
                candidates.append(["cmd", "/c", configured, "--stdio"])
            else:
                candidates.append([configured, "--stdio"])

        if self._config.venv_path is not None:
            scripts_dir = self._config.venv_path / ("Scripts" if os.name == "nt" else "bin")
            exe_suffix = ".exe" if os.name == "nt" else ""
            candidates.append([str(scripts_dir / f"pyright-langserver{exe_suffix}"), "--stdio"])
            if os.name == "nt":
                candidates.append(["cmd", "/c", str(scripts_dir / "pyright-langserver.cmd"), "--stdio"])

        # Deduplicate while preserving order.
        deduped: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()
        for command in candidates:
            command_key = tuple(command)
            if command_key in seen:
                continue
            seen.add(command_key)
            deduped.append(command)
        return deduped

    # ── Lifecycle ─────────────────────────────────────────────────────

    def _build_initialize_params(self) -> dict[str, JSONValue]:
        """Build LSP initialize params with full capability declarations."""
        root_uri = path_to_uri(str(self._config.workspace_root))
        return {
            "processId": None,
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "publishDiagnostics": {"relatedInformation": True},
                    "rename": {
                        "prepareSupport": True,
                        "prepareSupportDefaultBehavior": 1,
                    },
                    "semanticTokens": {
                        "requests": {"full": True},
                        "tokenTypes": SEMANTIC_TOKEN_TYPES,
                        "tokenModifiers": SEMANTIC_TOKEN_MODIFIERS,
                        "formats": ["relative"],
                    },
                },
                "workspace": {"workspaceFolders": True},
            },
            "workspaceFolders": [
                {
                    "uri": root_uri,
                    "name": self._config.workspace_root.name,
                }
            ],
            "clientInfo": {"name": "python-refactor-mcp"},
        }

    async def start(self) -> None:
        """Start the Pyright language server and initialize the LSP session."""
        initialize_params = self._build_initialize_params()

        startup_errors: list[str] = []
        for command in self._candidate_commands():
            self._client = self._make_client()
            try:
                await self._client.start(command)
                response = await asyncio.wait_for(
                    self._client.send_request("initialize", initialize_params),
                    timeout=15,
                )
                if "error" in response:
                    raise PyrightError(f"Pyright initialize failed: {response['error']}")
                await self._client.send_notification("initialized", {})
                settings: dict[str, JSONValue] = {
                    "python": {
                        "pythonPath": str(self._config.python_executable),
                        "analysis": {
                            "diagnosticMode": "openFilesOnly",
                            "autoSearchPaths": True,
                            "useLibraryCodeForTypes": True,
                        },
                    }
                }
                await self._client.send_notification(
                    "workspace/didChangeConfiguration",
                    {"settings": settings},
                )
                self._startup_command = command
                return
            except Exception as exc:
                startup_errors.append(f"{' '.join(command)} -> {exc}")
                await self._client.shutdown()

        joined_errors = " | ".join(startup_errors)
        raise PyrightError(f"Unable to start pyright language server. Attempts: {joined_errors}")

    async def shutdown(self) -> None:
        """Shutdown backend resources."""
        await self._client.shutdown()

    # ── File tracking ─────────────────────────────────────────────────

    async def ensure_file_open(self, file_path: str) -> None:
        """Ensure a file is opened and tracked in the language server session."""
        absolute_path = normalize_path(file_path)
        if absolute_path in self._open_files:
            return

        file_uri = path_to_uri(absolute_path)
        try:
            text = Path(absolute_path).read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise PyrightError(f"File not found: {absolute_path}") from exc
        except (UnicodeDecodeError, OSError) as exc:
            raise PyrightError(f"Cannot read file {absolute_path}: {exc}") from exc
        version = 1

        params: dict[str, JSONValue] = {
            "textDocument": {
                "uri": file_uri,
                "languageId": "python",
                "version": version,
                "text": text,
            }
        }
        await self._client.send_notification("textDocument/didOpen", params)
        self._open_files.add(absolute_path)
        self._file_versions[absolute_path] = version
        self._content_hashes[absolute_path] = hashlib.md5(text.encode()).hexdigest()

    async def _refresh_if_changed(self, absolute_path: str) -> None:
        """Re-read a file from disk and send didChange if its content has changed."""
        if absolute_path not in self._open_files:
            return
        try:
            text = Path(absolute_path).read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError, OSError):
            return
        new_hash = hashlib.md5(text.encode()).hexdigest()
        old_hash = self._content_hashes.get(absolute_path)
        if old_hash == new_hash:
            return
        # File changed on disk — send didChange to Pyright.
        version = self._file_versions.get(absolute_path, 1) + 1
        self._file_versions[absolute_path] = version
        self._content_hashes[absolute_path] = new_hash
        params: dict[str, JSONValue] = {
            "textDocument": {
                "uri": path_to_uri(absolute_path),
                "version": version,
            },
            "contentChanges": [{"text": text}],
        }
        await self._client.send_notification("textDocument/didChange", params)
        # Clear stale diagnostics so they get refreshed.
        self._diagnostics.pop(absolute_path, None)

    async def notify_file_changed(self, file_path: str) -> None:
        """Notify Pyright that a file's full contents changed."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        try:
            text = Path(absolute_path).read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise PyrightError(f"File not found: {absolute_path}") from exc
        except (UnicodeDecodeError, OSError) as exc:
            raise PyrightError(f"Cannot read file {absolute_path}: {exc}") from exc
        version = self._file_versions.get(absolute_path, 1) + 1
        self._file_versions[absolute_path] = version

        params: dict[str, JSONValue] = {
            "textDocument": {
                "uri": path_to_uri(absolute_path),
                "version": version,
            },
            "contentChanges": [{"text": text}],
        }
        await self._client.send_notification("textDocument/didChange", params)
        self._content_hashes[absolute_path] = hashlib.md5(text.encode()).hexdigest()

    # ── Diagnostics ───────────────────────────────────────────────────

    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]:
        """Return diagnostics for one file or the whole project."""
        if file_path is not None:
            normalized = normalize_path(file_path)
            await self.ensure_file_open(normalized)
            # Detect externally-modified files and refresh Pyright's view.
            await self._refresh_if_changed(normalized)
            if normalized not in self._diagnostics:
                event = self._diagnostics_events.setdefault(normalized, asyncio.Event())
                event.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(event.wait(), timeout=2.0)
            diagnostics = self._diagnostics.get(normalized, [])
        else:
            diagnostics = [item for items in self._diagnostics.values() for item in items]

        return sorted(
            diagnostics,
            key=lambda item: (
                item.file_path,
                item.range.start.line,
                item.range.start.character,
            ),
        )

    async def _handle_publish_diagnostics(self, params: JSONDict) -> None:
        """Handle textDocument/publishDiagnostics notifications from Pyright."""
        file_path, converted = convert_publish_diagnostics(params)
        if not file_path:
            return
        self._diagnostics[file_path] = converted
        event = self._diagnostics_events.get(file_path)
        if event is not None:
            event.set()

    # ── Analysis features ─────────────────────────────────────────────

    async def get_hover(self, file_path: str, line: int, char: int) -> TypeInfo | None:
        """Get hover type information at a source position."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/hover",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            raise PyrightError(f"Hover request failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, dict):
            return None

        contents_text = extract_hover_text(result.get("contents"))
        if not contents_text:
            return None

        first_line = contents_text.splitlines()[0].strip()
        return TypeInfo(
            expression=f"{absolute_path}:{line}:{char}",
            type_string=first_line,
            documentation=contents_text,
            source="pyright",
        )

    async def get_document_symbols(self, file_path: str) -> list[SymbolOutlineItem]:
        """Return hierarchical document symbols for a file."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/documentSymbol",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
            },
        )
        if "error" in response:
            raise PyrightError(f"documentSymbol request failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []

        symbols: list[SymbolOutlineItem] = []
        for entry in result:
            if not isinstance(entry, dict):
                continue
            converted = _convert_document_symbol(entry, absolute_path)
            if converted is not None:
                symbols.append(converted)

        return _reconstruct_symbol_hierarchy(symbols)

    async def get_completions(self, file_path: str, line: int, char: int) -> list[CompletionItem]:
        """Return completion candidates for a source position."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/completion",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            raise PyrightError(f"completion request failed: {response['error']}")

        result = response.get("result")
        items_value = result.get("items") if isinstance(result, dict) else result
        if not isinstance(items_value, list):
            return []

        completions: list[CompletionItem] = []
        seen: set[tuple[str, str, str]] = set()
        for entry in items_value:
            if not isinstance(entry, dict):
                continue
            label = as_str(entry.get("label"), "")
            if not label:
                continue
            kind_value = as_int(entry.get("kind", 1), 1)
            detail = as_str(entry.get("detail"), "") or None
            insert_text = as_str(entry.get("insertText"), "") or label
            documentation = extract_hover_text(entry.get("documentation")) or None
            key = (label, detail or "", insert_text)
            if key in seen:
                continue
            seen.add(key)
            completions.append(
                CompletionItem(
                    label=label,
                    kind=SYMBOL_KIND.get(kind_value, "text"),
                    detail=detail,
                    insert_text=insert_text,
                    documentation=documentation,
                )
            )
        return completions

    async def get_references(
        self,
        file_path: str,
        line: int,
        char: int,
        include_declaration: bool,
    ) -> list[Location]:
        """Get symbol references from Pyright."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/references",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
                "context": {"includeDeclaration": include_declaration},
            },
        )
        if "error" in response:
            raise PyrightError(f"References request failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []

        locations: list[Location] = []
        for entry in result:
            if not isinstance(entry, dict):
                continue
            uri_value = entry.get("uri")
            range_value = entry.get("range")
            if not isinstance(uri_value, str) or not isinstance(range_value, dict):
                continue
            locations.append(
                Location(
                    file_path=uri_to_path(uri_value),
                    range=model_range(range_value),
                )
            )
        return locations

    async def get_definition(self, file_path: str, line: int, char: int) -> list[Location]:
        """Get symbol definitions from Pyright."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/definition",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            raise PyrightError(f"Definition request failed: {response['error']}")

        result = response.get("result")
        if isinstance(result, dict):
            return definition_entry_to_locations(result)
        if isinstance(result, list):
            resolved: list[Location] = []
            for entry in result:
                if isinstance(entry, dict):
                    resolved.extend(definition_entry_to_locations(entry))
            return resolved
        return []

    async def get_implementation(self, file_path: str, line: int, char: int) -> list[Location]:
        """Get symbol implementation locations from Pyright."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/implementation",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            raise PyrightError(f"Implementation request failed: {response['error']}")

        result = response.get("result")
        if isinstance(result, dict):
            return definition_entry_to_locations(result)
        if isinstance(result, list):
            resolved: list[Location] = []
            for entry in result:
                if isinstance(entry, dict):
                    resolved.extend(definition_entry_to_locations(entry))
            return resolved
        return []

    async def get_signature_help(self, file_path: str, line: int, char: int) -> SignatureInfo | None:
        """Return signature help for a call position."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/signatureHelp",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            raise PyrightError(f"signatureHelp request failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, dict):
            return None

        signatures = result.get("signatures")
        if not isinstance(signatures, list) or not signatures:
            return None

        active_signature = as_int(result.get("activeSignature", 0), 0)
        if active_signature < 0 or active_signature >= len(signatures):
            active_signature = 0

        selected = signatures[active_signature]
        if not isinstance(selected, dict):
            return None

        label = as_str(selected.get("label"), "")
        if not label:
            return None

        raw_parameters = selected.get("parameters")
        parameters: list[ParameterInfo] = []
        if isinstance(raw_parameters, list):
            for parameter in raw_parameters:
                if not isinstance(parameter, dict):
                    continue
                raw_label = parameter.get("label")
                parameter_label = ""
                if isinstance(raw_label, str):
                    parameter_label = raw_label
                elif isinstance(raw_label, list) and len(raw_label) == 2:
                    start = as_int(raw_label[0], 0)
                    end = as_int(raw_label[1], 0)
                    if 0 <= start <= end <= len(label):
                        parameter_label = label[start:end]
                if not parameter_label:
                    continue
                parameters.append(
                    ParameterInfo(
                        label=parameter_label,
                        documentation=extract_hover_text(parameter.get("documentation")) or None,
                    )
                )

        active_parameter = result.get("activeParameter")
        active_parameter_value = as_int(active_parameter, 0) if isinstance(active_parameter, int) else None
        return SignatureInfo(
            label=label,
            parameters=parameters,
            active_parameter=active_parameter_value,
            active_signature=active_signature,
            documentation=extract_hover_text(selected.get("documentation")) or None,
        )

    async def workspace_symbol(self, query: str) -> list[SymbolInfo]:
        """Search workspace symbols by query string."""
        response = await self._request(
            "workspace/symbol",
            {"query": query},
        )
        if "error" in response:
            raise PyrightError(f"workspace/symbol request failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []

        symbols: list[SymbolInfo] = []
        seen: set[tuple[str, str, int, int, str]] = set()
        for entry in result:
            if not isinstance(entry, dict):
                continue

            name = as_str(entry.get("name"), "")
            if not name:
                continue

            location_value = entry.get("location")
            entry_file_path = ""
            range_value: JSONValue | None = None
            if isinstance(location_value, dict):
                uri_value = location_value.get("uri")
                range_value = location_value.get("range")
                if isinstance(uri_value, str):
                    entry_file_path = uri_to_path(uri_value)
            else:
                uri_value = entry.get("uri")
                range_value = entry.get("range")
                if isinstance(uri_value, str):
                    entry_file_path = uri_to_path(uri_value)

            if not entry_file_path or not isinstance(range_value, dict):
                continue

            entry_range = model_range(range_value)
            container_name = entry.get("containerName")
            key = (
                name, entry_file_path, entry_range.start.line,
                entry_range.start.character, as_str(container_name, ""),
            )
            if key in seen:
                continue
            seen.add(key)
            symbols.append(
                SymbolInfo(
                    name=name,
                    kind=SYMBOL_KIND.get(as_int(entry.get("kind", 13), 13), "symbol"),
                    file_path=entry_file_path,
                    range=entry_range,
                    container=container_name if isinstance(container_name, str) else None,
                )
            )
        return symbols

    # ── Hierarchy features ────────────────────────────────────────────

    async def prepare_call_hierarchy(
        self,
        file_path: str,
        line: int,
        char: int,
    ) -> list[CallHierarchyItem]:
        """Prepare call hierarchy item(s) for a position."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/prepareCallHierarchy",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            raise PyrightError(f"prepareCallHierarchy failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []
        return [call_hierarchy_item_to_model(item) for item in result if isinstance(item, dict)]

    async def get_incoming_calls(self, item: CallHierarchyItem) -> list[CallHierarchyItem]:
        """Return incoming call hierarchy items."""
        response = await self._request(
            "callHierarchy/incomingCalls",
            {"item": call_hierarchy_item_to_lsp(item)},
        )
        if "error" in response:
            raise PyrightError(f"incomingCalls failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []

        items: list[CallHierarchyItem] = []
        for entry in result:
            if not isinstance(entry, dict):
                continue
            source_item = entry.get("from")
            if isinstance(source_item, dict):
                items.append(call_hierarchy_item_to_model(source_item))
        return items

    async def get_outgoing_calls(self, item: CallHierarchyItem) -> list[CallHierarchyItem]:
        """Return outgoing call hierarchy items."""
        response = await self._request(
            "callHierarchy/outgoingCalls",
            {"item": call_hierarchy_item_to_lsp(item)},
        )
        if "error" in response:
            raise PyrightError(f"outgoingCalls failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []

        items: list[CallHierarchyItem] = []
        for entry in result:
            if not isinstance(entry, dict):
                continue
            target_item = entry.get("to")
            if isinstance(target_item, dict):
                items.append(call_hierarchy_item_to_model(target_item))
        return items

    async def prepare_type_hierarchy(self, file_path: str, line: int, char: int) -> list[TypeHierarchyItem]:
        """Prepare type hierarchy item(s) for a source position."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/prepareTypeHierarchy",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                return []
            raise PyrightError(f"prepareTypeHierarchy failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []
        return [type_hierarchy_item_to_model(item) for item in result if isinstance(item, dict)]

    async def get_supertypes(self, item: TypeHierarchyItem) -> list[TypeHierarchyItem]:
        """Return direct supertypes for a type hierarchy item."""
        response = await self._request(
            "typeHierarchy/supertypes",
            {"item": type_hierarchy_item_to_lsp(item)},
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                return []
            raise PyrightError(f"typeHierarchy/supertypes failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []
        return [type_hierarchy_item_to_model(entry) for entry in result if isinstance(entry, dict)]

    async def get_subtypes(self, item: TypeHierarchyItem) -> list[TypeHierarchyItem]:
        """Return direct subtypes for a type hierarchy item."""
        response = await self._request(
            "typeHierarchy/subtypes",
            {"item": type_hierarchy_item_to_lsp(item)},
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                return []
            raise PyrightError(f"typeHierarchy/subtypes failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []
        return [type_hierarchy_item_to_model(entry) for entry in result if isinstance(entry, dict)]

    # ── Selection / folding / highlights ──────────────────────────────

    async def get_selection_range(self, file_path: str, positions: list[Position]) -> list[SelectionRangeResult]:
        """Return nested selection ranges for one or more positions."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/selectionRange",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "positions": [
                    {"line": position.line, "character": position.character}
                    for position in positions
                ],
            },
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                return []
            raise PyrightError(f"selectionRange request failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []

        def _flatten_selection_ranges(item: JSONDict) -> list[Range]:
            flattened: list[Range] = []
            current: JSONValue = item
            while isinstance(current, dict):
                range_value = current.get("range")
                if isinstance(range_value, dict):
                    flattened.append(model_range(range_value))
                current = current.get("parent")
            return flattened

        mapped: list[SelectionRangeResult] = []
        for index, entry in enumerate(result):
            if not isinstance(entry, dict):
                continue
            if index >= len(positions):
                break
            mapped.append(
                SelectionRangeResult(
                    position=positions[index],
                    ranges=_flatten_selection_ranges(entry),
                )
            )
        return mapped

    async def get_code_actions(
        self,
        file_path: str,
        range_value: Range,
        diagnostics: list[Diagnostic],
    ) -> list[dict[str, object]]:
        """Return code action candidates for a range."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        lsp_diagnostics: list[JSONValue] = []
        for diagnostic in diagnostics:
            diagnostic_payload: JSONValue = {
                "range": {
                    "start": {
                        "line": diagnostic.range.start.line,
                        "character": diagnostic.range.start.character,
                    },
                    "end": {
                        "line": diagnostic.range.end.line,
                        "character": diagnostic.range.end.character,
                    },
                },
                "severity": severity_from_string(diagnostic.severity),
                "message": diagnostic.message,
                "code": diagnostic.code if diagnostic.code is not None else "",
            }
            lsp_diagnostics.append(diagnostic_payload)

        request_params: dict[str, JSONValue] = {
            "textDocument": {"uri": path_to_uri(absolute_path)},
            "range": {
                "start": {
                    "line": range_value.start.line,
                    "character": range_value.start.character,
                },
                "end": {
                    "line": range_value.end.line,
                    "character": range_value.end.character,
                },
            },
            "context": {"diagnostics": lsp_diagnostics},
        }
        response = await self._request("textDocument/codeAction", request_params)
        if "error" in response:
            raise PyrightError(f"codeAction request failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []

        actions: list[dict[str, object]] = []
        for item in result:
            if isinstance(item, dict):
                action: dict[str, object] = dict(item)
                actions.append(action)
        return actions

    async def get_declaration(self, file_path: str, line: int, char: int) -> list[Location]:
        """Get declaration locations for a symbol from Pyright."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/declaration",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                return await self.get_definition(file_path, line, char)
            raise PyrightError(f"Declaration request failed: {response['error']}")

        result = response.get("result")
        if isinstance(result, dict):
            return definition_entry_to_locations(result)
        if isinstance(result, list):
            resolved: list[Location] = []
            for entry in result:
                if isinstance(entry, dict):
                    resolved.extend(definition_entry_to_locations(entry))
            return resolved
        return []

    async def get_type_definition(self, file_path: str, line: int, char: int) -> list[Location]:
        """Get type-definition locations for a symbol from Pyright."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/typeDefinition",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                return []
            raise PyrightError(f"typeDefinition request failed: {response['error']}")

        result = response.get("result")
        if isinstance(result, dict):
            return definition_entry_to_locations(result)
        if isinstance(result, list):
            resolved: list[Location] = []
            for entry in result:
                if isinstance(entry, dict):
                    resolved.extend(definition_entry_to_locations(entry))
            return resolved
        return []

    async def get_document_highlights(self, file_path: str, line: int, char: int) -> list[DocumentHighlight]:
        """Get in-file highlights for a symbol at the provided position."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/documentHighlight",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            raise PyrightError(f"documentHighlight request failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []

        highlights: list[DocumentHighlight] = []
        for entry in result:
            if not isinstance(entry, dict):
                continue
            range_value = entry.get("range")
            if not isinstance(range_value, dict):
                continue
            kind = DOCUMENT_HIGHLIGHT_KIND.get(as_int(entry.get("kind", 1), 1), "text")
            highlights.append(DocumentHighlight(range=model_range(range_value), kind=kind))
        return highlights

    async def prepare_rename(self, file_path: str, line: int, char: int) -> PrepareRenameResult | None:
        """Run LSP rename preflight and return editable range metadata if valid."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/prepareRename",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                return None
            raise PyrightError(f"prepareRename request failed: {response['error']}")

        result = response.get("result")
        if result is None:
            return None

        if isinstance(result, dict) and "range" not in result:
            return None

        if isinstance(result, dict):
            range_value = result.get("range")
            placeholder = as_str(result.get("placeholder"), "")
        else:
            range_value = result
            placeholder = ""

        if not isinstance(range_value, dict):
            return None

        if not placeholder:
            try:
                source_lines = Path(absolute_path).read_text(encoding="utf-8").splitlines()
                mr = model_range(range_value)
                start_line = mr.start.line
                if 0 <= start_line < len(source_lines):
                    line_text = source_lines[start_line]
                    start_char = mr.start.character
                    end_char = mr.end.character if mr.end.line == start_line else len(line_text)
                    placeholder = line_text[start_char:end_char].strip() or Path(absolute_path).stem
                else:
                    placeholder = Path(absolute_path).stem
            except Exception:
                placeholder = Path(absolute_path).stem

        return PrepareRenameResult(range=model_range(range_value), placeholder=placeholder)

    async def get_inlay_hints(
        self,
        file_path: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
    ) -> list[InlayHint]:
        """Get inlay hints for the provided file range."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/inlayHint",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "range": {
                    "start": {"line": start_line, "character": start_character},
                    "end": {"line": end_line, "character": end_character},
                },
            },
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                return []
            raise PyrightError(f"inlayHint request failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []

        hints: list[InlayHint] = []
        for entry in result:
            if not isinstance(entry, dict):
                continue
            position_value = entry.get("position")
            if not isinstance(position_value, dict):
                continue
            raw_label = entry.get("label")
            if isinstance(raw_label, str):
                label = raw_label
            elif isinstance(raw_label, list):
                parts: list[str] = []
                for part in raw_label:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict):
                        part_value = part.get("value")
                        if isinstance(part_value, str):
                            parts.append(part_value)
                label = "".join(parts)
            else:
                label = ""
            if not label:
                continue
            hint_kind = None
            kind_value = entry.get("kind")
            if isinstance(kind_value, int):
                hint_kind = {1: "type", 2: "parameter"}.get(kind_value, "unknown")
            hints.append(
                InlayHint(
                    position=model_position(position_value),
                    label=label,
                    kind=hint_kind,
                    padding_left=bool(entry.get("paddingLeft", False)),
                    padding_right=bool(entry.get("paddingRight", False)),
                )
            )
        return hints

    async def get_semantic_tokens(self, file_path: str) -> list[SemanticToken]:
        """Get and decode full-document semantic tokens from Pyright."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/semanticTokens/full",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
            },
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                return []
            raise PyrightError(f"semanticTokens/full request failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, dict):
            return []
        data = result.get("data")
        if not isinstance(data, list):
            return []

        numbers: list[int] = [value for value in data if isinstance(value, int)]
        tokens: list[SemanticToken] = []
        line = 0
        character = 0
        for index in range(0, len(numbers), 5):
            if index + 4 >= len(numbers):
                break
            delta_line = numbers[index]
            delta_char = numbers[index + 1]
            length = numbers[index + 2]
            token_type_idx = numbers[index + 3]
            modifiers_bits = numbers[index + 4]

            if delta_line == 0:
                character += delta_char
            else:
                line += delta_line
                character = delta_char

            token_type = (
                SEMANTIC_TOKEN_TYPES[token_type_idx]
                if 0 <= token_type_idx < len(SEMANTIC_TOKEN_TYPES)
                else "unknown"
            )
            modifiers: list[str] = []
            for bit, modifier_name in enumerate(SEMANTIC_TOKEN_MODIFIERS):
                if modifiers_bits & (1 << bit):
                    modifiers.append(modifier_name)

            tokens.append(
                SemanticToken(
                    range=Range(
                        start=Position(line=line, character=character),
                        end=Position(line=line, character=character + max(length, 0)),
                    ),
                    token_type=token_type,
                    modifiers=modifiers,
                )
            )
        return tokens

    async def get_folding_ranges(self, file_path: str) -> list[FoldingRange]:
        """Get foldable regions for a file from Pyright."""
        absolute_path = normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/foldingRange",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
            },
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                return []
            raise PyrightError(f"foldingRange request failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []

        ranges: list[FoldingRange] = []
        for entry in result:
            if not isinstance(entry, dict):
                continue
            start_line = entry.get("startLine")
            end_line = entry.get("endLine")
            if not isinstance(start_line, int) or not isinstance(end_line, int):
                continue
            kind_value = entry.get("kind")
            kind = kind_value if isinstance(kind_value, str) else None
            ranges.append(FoldingRange(start_line=start_line, end_line=end_line, kind=kind))
        return ranges

    async def create_type_stub(self, package_name: str, output_dir: str | None = None) -> bool:
        """Generate a type stub file for a third-party package using Pyright.

        Returns True if the command executed successfully.
        """
        args: list[object] = [package_name]
        if output_dir is not None:
            args.append(output_dir)
        response = await self._request(
            "workspace/executeCommand",
            {
                "command": "pyright.createtypestub",
                "arguments": args,
            },
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                raise PyrightError(
                    "createtypestub is not supported by this version of Pyright"
                )
            raise PyrightError(f"createtypestub failed: {response['error']}")
        return True

    async def restart_server(self) -> str:
        """Restart Pyright analysis, discarding cached type information."""
        response = await self._request(
            "workspace/executeCommand",
            {
                "command": "pyright.restartserver",
                "arguments": [],
            },
        )
        self._diagnostics.clear()
        self._file_versions.clear()
        self._content_hashes.clear()
        self._open_files.clear()
        self._diagnostics_events.clear()
        if "error" in response:
            if is_unhandled_method_error(response):
                _LOGGER.debug("pyright.restartserver not supported, performing manual restart")
                await self.shutdown()
                await self.start()
                return "Pyright server restarted (manual restart)"
            raise PyrightError(f"restartserver failed: {response['error']}")
        return "Pyright server restarted successfully"
