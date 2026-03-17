"""Pyright language server backend over async JSON-RPC/LSP transport."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import PyrightError
from python_refactor_mcp.models import CallHierarchyItem, Diagnostic, Location, Position, Range, TypeInfo
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


class PyrightLSPClient:
    """Pyright backend that wraps language-server calls with model conversion."""

    def __init__(self, config: ServerConfig) -> None:
        """Initialize the Pyright backend with server config."""
        self._config = config
        self._client = LSPClient()
        self._open_files: set[str] = set()
        self._file_versions: dict[str, int] = {}
        self._diagnostics: dict[str, list[Diagnostic]] = {}
        self._client.register_notification_handler(
            "textDocument/publishDiagnostics",
            self._handle_publish_diagnostics,
        )

    async def start(self) -> None:
        """Start the Pyright language server and initialize the LSP session."""
        command = [self._config.pyright_executable, "--stdio"]
        await self._client.start(command)

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

        response = await self._client.send_request("initialize", initialize_params)
        if "error" in response:
            raise PyrightError(f"Pyright initialize failed: {response['error']}")

        await self._client.send_notification("initialized", {})

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

        response = await self._client.send_request(
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

        response = await self._client.send_request(
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

        response = await self._client.send_request(
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

    async def prepare_call_hierarchy(
        self,
        file_path: str,
        line: int,
        char: int,
    ) -> list[CallHierarchyItem]:
        """Prepare call hierarchy item(s) for a position."""
        absolute_path = _normalize_path(file_path)
        await self.ensure_file_open(absolute_path)

        response = await self._client.send_request(
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
        response = await self._client.send_request(
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
        response = await self._client.send_request(
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
        response = await self._client.send_request("textDocument/codeAction", request_params)
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

    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]:
        """Return diagnostics for one file or the whole project."""
        if file_path is not None:
            normalized = _normalize_path(file_path)
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

            converted.append(
                Diagnostic(
                    file_path=file_path,
                    range=_model_range(range_value),
                    severity=_severity_to_string(_as_int(severity_value, 3)),
                    message=message_value,
                    code=code,
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
    def _severity_from_string(severity: str) -> int:
        """Convert string severity labels into LSP numeric severity."""
        mapping = {"error": 1, "warning": 2, "information": 3, "hint": 4}
        return mapping.get(severity.lower(), 3)
