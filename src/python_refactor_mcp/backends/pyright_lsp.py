"""Pyright language server backend over async JSON-RPC/LSP transport."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

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

_SYMBOL_KIND: dict[int, str] = {
    1: "file",
    2: "module",
    3: "namespace",
    4: "package",
    5: "class",
    6: "method",
    7: "property",
    8: "field",
    9: "constructor",
    10: "enum",
    11: "interface",
    12: "function",
    13: "variable",
    14: "constant",
    15: "string",
    16: "number",
    17: "boolean",
    18: "array",
    19: "object",
    20: "key",
    21: "null",
    22: "enumMember",
    23: "struct",
    24: "event",
    25: "operator",
    26: "typeParameter",
}

_DOCUMENT_HIGHLIGHT_KIND: dict[int, str] = {1: "text", 2: "read", 3: "write"}
_SEMANTIC_TOKEN_TYPES: list[str] = [
    "namespace",
    "type",
    "class",
    "enum",
    "interface",
    "struct",
    "typeParameter",
    "parameter",
    "variable",
    "property",
    "enumMember",
    "event",
    "function",
    "method",
    "macro",
    "keyword",
    "modifier",
    "comment",
    "string",
    "number",
    "regexp",
    "operator",
    "decorator",
]
_SEMANTIC_TOKEN_MODIFIERS: list[str] = [
    "declaration",
    "definition",
    "readonly",
    "static",
    "deprecated",
    "abstract",
    "async",
    "modification",
    "documentation",
    "defaultLibrary",
]


def _normalize_path(file_path: str) -> str:
    """Return a normalized absolute path with stable Windows drive casing."""
    absolute = os.path.abspath(file_path)
    if os.name == "nt" and len(absolute) >= 2 and absolute[1] == ":":
        absolute = absolute[0].upper() + absolute[1:]
    return absolute


def path_to_uri(path: str) -> str:
    """Convert an OS-native path into a file URI."""
    return Path(_normalize_path(path)).as_uri()


def uri_to_path(uri: str) -> str:
    """Convert a file URI to an OS-native absolute path."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise PyrightError(f"Unsupported URI scheme for path conversion: {uri}")

    decoded_path = unquote(parsed.path)
    if os.name == "nt":
        if decoded_path.startswith("/") and len(decoded_path) >= 3 and decoded_path[2] == ":":
            decoded_path = decoded_path[1:]
        decoded_path = decoded_path.replace("/", "\\")
    return _normalize_path(decoded_path)


def _as_int(value: JSONValue, fallback: int = 0) -> int:
    """Convert a JSON value to int when possible, otherwise return fallback."""
    if isinstance(value, int):
        return value
    return fallback


def _as_str(value: JSONValue, fallback: str = "") -> str:
    """Convert a JSON value to str when possible, otherwise return fallback."""
    if isinstance(value, str):
        return value
    return fallback


def _model_position(value: JSONDict) -> Position:
    """Convert an LSP position dict into a Position model."""
    return Position(
        line=_as_int(value.get("line", 0), 0),
        character=_as_int(value.get("character", 0), 0),
    )


def _model_range(value: JSONDict) -> Range:
    """Convert an LSP range dict into a Range model."""
    start = value.get("start")
    end = value.get("end")
    if not isinstance(start, dict) or not isinstance(end, dict):
        return Range(start=Position(line=0, character=0), end=Position(line=0, character=0))
    return Range(start=_model_position(start), end=_model_position(end))


def _severity_to_string(value: int) -> str:
    """Map LSP diagnostic severity numbers to string labels."""
    mapping = {1: "error", 2: "warning", 3: "information", 4: "hint"}
    return mapping.get(value, "information")


def _is_unhandled_method_error(response: JSONDict) -> bool:
    """Return True when server reports an unsupported/unhandled LSP method."""
    error_value = response.get("error")
    if not isinstance(error_value, dict):
        return False
    code = error_value.get("code")
    message = error_value.get("message")
    if code == -32601:
        return True
    return isinstance(message, str) and "Unhandled method" in message


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
        self._diagnostics: dict[str, list[Diagnostic]] = {}

    async def _request(self, method: str, params: dict[str, JSONValue]) -> JSONDict:
        """Send an LSP request with a bounded timeout for backend resilience."""
        try:
            return await asyncio.wait_for(
                self._client.send_request(method, params),
                timeout=self._request_timeout_seconds,
            )
        except TimeoutError as exc:
            raise PyrightError(
                f"{method} request timed out after {self._request_timeout_seconds:.1f}s"
            ) from exc

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

    async def start(self) -> None:
        """Start the Pyright language server and initialize the LSP session."""
        root_uri = path_to_uri(str(self._config.workspace_root))
        initialize_params: dict[str, JSONValue] = {
            "processId": None,
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "publishDiagnostics": {"relatedInformation": True},
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
                return
            except Exception as exc:
                startup_errors.append(f"{' '.join(command)} -> {exc}")
                await self._client.shutdown()

        joined_errors = " | ".join(startup_errors)
        raise PyrightError(f"Unable to start pyright language server. Attempts: {joined_errors}")

    async def ensure_file_open(self, file_path: str) -> None:
        """Ensure a file is opened and tracked in the language server session."""
        absolute_path = _normalize_path(file_path)
        if absolute_path in self._open_files:
            return

        file_uri = path_to_uri(absolute_path)
        text = Path(absolute_path).read_text(encoding="utf-8")
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

    async def notify_file_changed(self, file_path: str) -> None:
        """Notify Pyright that a file's full contents changed."""
        absolute_path = _normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        text = Path(absolute_path).read_text(encoding="utf-8")
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

    async def get_hover(self, file_path: str, line: int, char: int) -> TypeInfo | None:
        """Get hover type information at a source position."""
        absolute_path = _normalize_path(file_path)
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

        contents_text = self._extract_hover_text(result.get("contents"))
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
        absolute_path = _normalize_path(file_path)
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

        def _convert_document_symbol(entry: JSONDict, fallback_path: str) -> SymbolOutlineItem | None:
            name = _as_str(entry.get("name"), "")
            if not name:
                return None

            kind_value = _as_int(entry.get("kind", 13), 13)
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
                kind=_SYMBOL_KIND.get(kind_value, "symbol"),
                file_path=resolved_path,
                range=_model_range(range_value),
                selection_range=_model_range(selection_value),
                detail=_as_str(entry.get("detail"), "") or None,
                container=container if isinstance(container, str) else None,
                children=children,
            )

        symbols: list[SymbolOutlineItem] = []
        for entry in result:
            if not isinstance(entry, dict):
                continue
            converted = _convert_document_symbol(entry, absolute_path)
            if converted is not None:
                symbols.append(converted)
        return symbols

    async def get_completions(self, file_path: str, line: int, char: int) -> list[CompletionItem]:
        """Return completion candidates for a source position."""
        absolute_path = _normalize_path(file_path)
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
            label = _as_str(entry.get("label"), "")
            if not label:
                continue
            kind_value = _as_int(entry.get("kind", 1), 1)
            detail = _as_str(entry.get("detail"), "") or None
            insert_text = _as_str(entry.get("insertText"), "") or label
            documentation = self._extract_hover_text(entry.get("documentation")) or None
            key = (label, detail or "", insert_text)
            if key in seen:
                continue
            seen.add(key)
            completions.append(
                CompletionItem(
                    label=label,
                    kind=_SYMBOL_KIND.get(kind_value, "text"),
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
        absolute_path = _normalize_path(file_path)
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
                    range=_model_range(range_value),
                )
            )
        return locations

    async def get_definition(self, file_path: str, line: int, char: int) -> list[Location]:
        """Get symbol definitions from Pyright."""
        absolute_path = _normalize_path(file_path)
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
            return self._definition_entry_to_locations(result)
        if isinstance(result, list):
            resolved: list[Location] = []
            for entry in result:
                if isinstance(entry, dict):
                    resolved.extend(self._definition_entry_to_locations(entry))
            return resolved
        return []

    async def get_implementation(self, file_path: str, line: int, char: int) -> list[Location]:
        """Get symbol implementation locations from Pyright."""
        absolute_path = _normalize_path(file_path)
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
            return self._definition_entry_to_locations(result)
        if isinstance(result, list):
            resolved: list[Location] = []
            for entry in result:
                if isinstance(entry, dict):
                    resolved.extend(self._definition_entry_to_locations(entry))
            return resolved
        return []

    async def get_signature_help(self, file_path: str, line: int, char: int) -> SignatureInfo | None:
        """Return signature help for a call position."""
        absolute_path = _normalize_path(file_path)
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

        active_signature = _as_int(result.get("activeSignature", 0), 0)
        if active_signature < 0 or active_signature >= len(signatures):
            active_signature = 0

        selected = signatures[active_signature]
        if not isinstance(selected, dict):
            return None

        label = _as_str(selected.get("label"), "")
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
                    start = _as_int(raw_label[0], 0)
                    end = _as_int(raw_label[1], 0)
                    if 0 <= start <= end <= len(label):
                        parameter_label = label[start:end]
                if not parameter_label:
                    continue
                parameters.append(
                    ParameterInfo(
                        label=parameter_label,
                        documentation=self._extract_hover_text(parameter.get("documentation")) or None,
                    )
                )

        active_parameter = result.get("activeParameter")
        active_parameter_value = _as_int(active_parameter, 0) if isinstance(active_parameter, int) else None
        return SignatureInfo(
            label=label,
            parameters=parameters,
            active_parameter=active_parameter_value,
            active_signature=active_signature,
            documentation=self._extract_hover_text(selected.get("documentation")) or None,
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

            name = _as_str(entry.get("name"), "")
            if not name:
                continue

            location_value = entry.get("location")
            file_path = ""
            range_value: JSONValue | None = None
            if isinstance(location_value, dict):
                uri_value = location_value.get("uri")
                range_value = location_value.get("range")
                if isinstance(uri_value, str):
                    file_path = uri_to_path(uri_value)
            else:
                uri_value = entry.get("uri")
                range_value = entry.get("range")
                if isinstance(uri_value, str):
                    file_path = uri_to_path(uri_value)

            if not file_path or not isinstance(range_value, dict):
                continue

            model_range = _model_range(range_value)
            container_name = entry.get("containerName")
            key = (name, file_path, model_range.start.line, model_range.start.character, _as_str(container_name, ""))
            if key in seen:
                continue
            seen.add(key)
            symbols.append(
                SymbolInfo(
                    name=name,
                    kind=_SYMBOL_KIND.get(_as_int(entry.get("kind", 13), 13), "symbol"),
                    file_path=file_path,
                    range=model_range,
                    container=container_name if isinstance(container_name, str) else None,
                )
            )
        return symbols

    async def prepare_call_hierarchy(
        self,
        file_path: str,
        line: int,
        char: int,
    ) -> list[CallHierarchyItem]:
        """Prepare call hierarchy item(s) for a position."""
        absolute_path = _normalize_path(file_path)
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
        return [self._call_hierarchy_item_to_model(item) for item in result if isinstance(item, dict)]

    async def get_incoming_calls(self, item: CallHierarchyItem) -> list[CallHierarchyItem]:
        """Return incoming call hierarchy items."""
        response = await self._request(
            "callHierarchy/incomingCalls",
            {"item": self._call_hierarchy_item_to_lsp(item)},
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
                items.append(self._call_hierarchy_item_to_model(source_item))
        return items

    async def get_outgoing_calls(self, item: CallHierarchyItem) -> list[CallHierarchyItem]:
        """Return outgoing call hierarchy items."""
        response = await self._request(
            "callHierarchy/outgoingCalls",
            {"item": self._call_hierarchy_item_to_lsp(item)},
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
                items.append(self._call_hierarchy_item_to_model(target_item))
        return items

    async def prepare_type_hierarchy(self, file_path: str, line: int, char: int) -> list[TypeHierarchyItem]:
        """Prepare type hierarchy item(s) for a source position."""
        absolute_path = _normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/prepareTypeHierarchy",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            if _is_unhandled_method_error(response):
                return []
            raise PyrightError(f"prepareTypeHierarchy failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []
        return [self._type_hierarchy_item_to_model(item) for item in result if isinstance(item, dict)]

    async def get_supertypes(self, item: TypeHierarchyItem) -> list[TypeHierarchyItem]:
        """Return direct supertypes for a type hierarchy item."""
        response = await self._request(
            "typeHierarchy/supertypes",
            {"item": self._type_hierarchy_item_to_lsp(item)},
        )
        if "error" in response:
            if _is_unhandled_method_error(response):
                return []
            raise PyrightError(f"typeHierarchy/supertypes failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []
        return [self._type_hierarchy_item_to_model(entry) for entry in result if isinstance(entry, dict)]

    async def get_subtypes(self, item: TypeHierarchyItem) -> list[TypeHierarchyItem]:
        """Return direct subtypes for a type hierarchy item."""
        response = await self._request(
            "typeHierarchy/subtypes",
            {"item": self._type_hierarchy_item_to_lsp(item)},
        )
        if "error" in response:
            if _is_unhandled_method_error(response):
                return []
            raise PyrightError(f"typeHierarchy/subtypes failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []
        return [self._type_hierarchy_item_to_model(entry) for entry in result if isinstance(entry, dict)]

    async def get_selection_range(self, file_path: str, positions: list[Position]) -> list[SelectionRangeResult]:
        """Return nested selection ranges for one or more positions."""
        absolute_path = _normalize_path(file_path)
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
            if _is_unhandled_method_error(response):
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
                    flattened.append(_model_range(range_value))
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
        absolute_path = _normalize_path(file_path)
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
                "severity": self._severity_from_string(diagnostic.severity),
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
        absolute_path = _normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/declaration",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            if _is_unhandled_method_error(response):
                return await self.get_definition(file_path, line, char)
            raise PyrightError(f"Declaration request failed: {response['error']}")

        result = response.get("result")
        if isinstance(result, dict):
            return self._definition_entry_to_locations(result)
        if isinstance(result, list):
            resolved: list[Location] = []
            for entry in result:
                if isinstance(entry, dict):
                    resolved.extend(self._definition_entry_to_locations(entry))
            return resolved
        return []

    async def get_type_definition(self, file_path: str, line: int, char: int) -> list[Location]:
        """Get type-definition locations for a symbol from Pyright."""
        absolute_path = _normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/typeDefinition",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            if _is_unhandled_method_error(response):
                return []
            raise PyrightError(f"typeDefinition request failed: {response['error']}")

        result = response.get("result")
        if isinstance(result, dict):
            return self._definition_entry_to_locations(result)
        if isinstance(result, list):
            resolved: list[Location] = []
            for entry in result:
                if isinstance(entry, dict):
                    resolved.extend(self._definition_entry_to_locations(entry))
            return resolved
        return []

    async def get_document_highlights(self, file_path: str, line: int, char: int) -> list[DocumentHighlight]:
        """Get in-file highlights for a symbol at the provided position."""
        absolute_path = _normalize_path(file_path)
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
            kind = _DOCUMENT_HIGHLIGHT_KIND.get(_as_int(entry.get("kind", 1), 1), "text")
            highlights.append(DocumentHighlight(range=_model_range(range_value), kind=kind))
        return highlights

    async def prepare_rename(self, file_path: str, line: int, char: int) -> PrepareRenameResult | None:
        """Run LSP rename preflight and return editable range metadata if valid."""
        absolute_path = _normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/prepareRename",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "position": {"line": line, "character": char},
            },
        )
        if "error" in response:
            if _is_unhandled_method_error(response):
                return None
            raise PyrightError(f"prepareRename request failed: {response['error']}")

        result = response.get("result")
        if result is None:
            return None

        if isinstance(result, dict) and "range" not in result:
            return None

        if isinstance(result, dict):
            range_value = result.get("range")
            placeholder = _as_str(result.get("placeholder"), "")
        else:
            range_value = result
            placeholder = ""

        if not isinstance(range_value, dict):
            return None

        if not placeholder:
            placeholder = Path(absolute_path).stem

        return PrepareRenameResult(range=_model_range(range_value), placeholder=placeholder)

    async def get_inlay_hints(
        self,
        file_path: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
    ) -> list[InlayHint]:
        """Get inlay hints for the provided file range."""
        absolute_path = _normalize_path(file_path)
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
            if _is_unhandled_method_error(response):
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
                    position=_model_position(position_value),
                    label=label,
                    kind=hint_kind,
                    padding_left=bool(entry.get("paddingLeft", False)),
                    padding_right=bool(entry.get("paddingRight", False)),
                )
            )
        return hints

    async def get_semantic_tokens(self, file_path: str) -> list[SemanticToken]:
        """Get and decode full-document semantic tokens from Pyright."""
        absolute_path = _normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/semanticTokens/full",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
            },
        )
        if "error" in response:
            if _is_unhandled_method_error(response):
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
                _SEMANTIC_TOKEN_TYPES[token_type_idx]
                if 0 <= token_type_idx < len(_SEMANTIC_TOKEN_TYPES)
                else "unknown"
            )
            modifiers: list[str] = []
            for bit, modifier_name in enumerate(_SEMANTIC_TOKEN_MODIFIERS):
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
        absolute_path = _normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._request(
            "textDocument/foldingRange",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
            },
        )
        if "error" in response:
            if _is_unhandled_method_error(response):
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

    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]:
        """Return diagnostics for one file or the whole project."""
        if file_path is not None:
            normalized = _normalize_path(file_path)
            await self.ensure_file_open(normalized)
            if normalized not in self._diagnostics:
                for _ in range(10):
                    await asyncio.sleep(0.05)
                    if normalized in self._diagnostics:
                        break
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

    async def shutdown(self) -> None:
        """Shutdown backend resources."""
        await self._client.shutdown()

    async def _handle_publish_diagnostics(self, params: JSONDict) -> None:
        """Handle textDocument/publishDiagnostics notifications from Pyright."""
        uri_value = params.get("uri")
        diagnostics_value = params.get("diagnostics")
        if not isinstance(uri_value, str) or not isinstance(diagnostics_value, list):
            return

        file_path = uri_to_path(uri_value)
        converted: list[Diagnostic] = []
        for entry in diagnostics_value:
            if not isinstance(entry, dict):
                continue

            range_value = entry.get("range")
            message_value = entry.get("message")
            severity_value = entry.get("severity")
            code_value = entry.get("code")

            if not isinstance(range_value, dict) or not isinstance(message_value, str):
                continue

            code: str | None = None
            if isinstance(code_value, str):
                code = code_value
            elif isinstance(code_value, int):
                code = str(code_value)

            tags_value = entry.get("tags")
            tags: list[int] = []
            if isinstance(tags_value, list):
                tags = [tag for tag in tags_value if isinstance(tag, int)]

            converted.append(
                Diagnostic(
                    file_path=file_path,
                    range=_model_range(range_value),
                    severity=_severity_to_string(_as_int(severity_value, 3)),
                    message=message_value,
                    code=code,
                    tags=tags,
                )
            )

        self._diagnostics[file_path] = converted

    @staticmethod
    def _extract_hover_text(contents: JSONValue) -> str:
        """Flatten hover contents into a single text blob."""
        if isinstance(contents, str):
            return contents
        if isinstance(contents, dict):
            value = contents.get("value")
            if isinstance(value, str):
                return value
            return ""
        if isinstance(contents, list):
            chunks: list[str] = []
            for item in contents:
                flattened = PyrightLSPClient._extract_hover_text(item)
                if flattened:
                    chunks.append(flattened)
            return "\n".join(chunks)
        return ""

    @staticmethod
    def _definition_entry_to_locations(entry: JSONDict) -> list[Location]:
        """Convert definition response entries (Location/LocationLink) into models."""
        if "uri" in entry and "range" in entry:
            uri_value = entry.get("uri")
            range_value = entry.get("range")
            if isinstance(uri_value, str) and isinstance(range_value, dict):
                return [Location(file_path=uri_to_path(uri_value), range=_model_range(range_value))]

        target_uri = entry.get("targetUri")
        target_range = entry.get("targetSelectionRange")
        if not isinstance(target_range, dict):
            target_range = entry.get("targetRange")
        if isinstance(target_uri, str) and isinstance(target_range, dict):
            return [Location(file_path=uri_to_path(target_uri), range=_model_range(target_range))]

        return []

    @staticmethod
    def _call_hierarchy_item_to_model(item: JSONDict) -> CallHierarchyItem:
        """Convert an LSP call hierarchy item payload to the project model."""
        uri = _as_str(item.get("uri"), "")
        range_value = item.get("selectionRange")
        if not isinstance(range_value, dict):
            range_value = item.get("range")

        model_range = _model_range(range_value) if isinstance(range_value, dict) else Range(
            start=Position(line=0, character=0),
            end=Position(line=0, character=0),
        )

        kind_number = _as_int(item.get("kind"), 13)
        return CallHierarchyItem(
            name=_as_str(item.get("name"), ""),
            kind=_SYMBOL_KIND.get(kind_number, "symbol"),
            file_path=uri_to_path(uri) if uri else "",
            range=model_range,
            detail=_as_str(item.get("detail"), "") or None,
        )

    @staticmethod
    def _call_hierarchy_item_to_lsp(item: CallHierarchyItem) -> dict[str, JSONValue]:
        """Convert project call hierarchy model to LSP item payload."""
        return {
            "name": item.name,
            "kind": 12,
            "uri": path_to_uri(item.file_path),
            "range": {
                "start": {
                    "line": item.range.start.line,
                    "character": item.range.start.character,
                },
                "end": {
                    "line": item.range.end.line,
                    "character": item.range.end.character,
                },
            },
            "selectionRange": {
                "start": {
                    "line": item.range.start.line,
                    "character": item.range.start.character,
                },
                "end": {
                    "line": item.range.end.line,
                    "character": item.range.end.character,
                },
            },
            "detail": item.detail or "",
        }

    @staticmethod
    def _type_hierarchy_item_to_model(item: JSONDict) -> TypeHierarchyItem:
        """Convert an LSP type hierarchy payload to the project model."""
        uri = _as_str(item.get("uri"), "")
        range_value = item.get("selectionRange")
        if not isinstance(range_value, dict):
            range_value = item.get("range")
        model_range = _model_range(range_value) if isinstance(range_value, dict) else Range(
            start=Position(line=0, character=0),
            end=Position(line=0, character=0),
        )
        kind_number = _as_int(item.get("kind"), 5)
        return TypeHierarchyItem(
            name=_as_str(item.get("name"), ""),
            kind=_SYMBOL_KIND.get(kind_number, "class"),
            file_path=uri_to_path(uri) if uri else "",
            range=model_range,
            detail=_as_str(item.get("detail"), "") or None,
        )

    @staticmethod
    def _type_hierarchy_item_to_lsp(item: TypeHierarchyItem) -> dict[str, JSONValue]:
        """Convert type hierarchy model to LSP TypeHierarchyItem payload."""
        return {
            "name": item.name,
            "kind": 5,
            "uri": path_to_uri(item.file_path),
            "range": {
                "start": {"line": item.range.start.line, "character": item.range.start.character},
                "end": {"line": item.range.end.line, "character": item.range.end.character},
            },
            "selectionRange": {
                "start": {"line": item.range.start.line, "character": item.range.start.character},
                "end": {"line": item.range.end.line, "character": item.range.end.character},
            },
            "detail": item.detail or "",
        }

    @staticmethod
    def _severity_from_string(severity: str) -> int:
        """Convert string severity labels into LSP numeric severity."""
        mapping = {"error": 1, "warning": 2, "information": 3, "hint": 4}
        return mapping.get(severity.lower(), 3)
