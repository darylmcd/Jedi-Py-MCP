"""Unit tests for LSP transport and Pyright backend behavior."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import cast

import pytest

from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient, path_to_uri, uri_to_path
from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import CallHierarchyItem, Position, Range
from python_refactor_mcp.util.lsp_client import (
    JSONDict,
    JSONValue,
    LSPClient,
    encode_lsp_message,
    read_lsp_message,
)


class FakeLSPClient:
    """Simple fake transport for Pyright backend unit tests."""

    def __init__(self, responses: dict[str, JSONDict | None] | None = None) -> None:
        self._responses = responses or {}
        self.notifications: list[tuple[str, dict[str, JSONValue]]] = []
        self.requests: list[tuple[str, dict[str, JSONValue]]] = []
        self.handlers: dict[str, object] = {}

    def is_alive(self) -> bool:
        return True

    def register_notification_handler(self, method: str, handler: object) -> None:
        self.handlers[method] = handler

    async def start(self, command: list[str]) -> None:
        _ = command

    async def send_request(self, method: str, params: dict[str, JSONValue]) -> JSONDict:
        self.requests.append((method, params))
        return self._responses.get(method, {"jsonrpc": "2.0", "id": 1, "result": None}) or {
            "jsonrpc": "2.0",
            "id": 1,
            "result": None,
        }

    async def send_notification(self, method: str, params: dict[str, JSONValue]) -> None:
        self.notifications.append((method, params))

    async def shutdown(self) -> None:
        return


class LSPClientHarness(LSPClient):
    """Test helper exposing narrow wrappers around protected internals."""

    def add_pending_future(self, request_id: int, future: asyncio.Future[JSONDict]) -> None:
        """Attach a pending future keyed by request id."""
        self._pending[request_id] = future

    async def route_message(self, message: JSONDict) -> None:
        """Route a decoded message through the internal dispatcher."""
        await self._route_message(message)


class PyrightClientHarness(PyrightLSPClient):
    """Test helper allowing transport replacement without external protected access."""

    def set_client(self, client: LSPClient) -> None:
        """Replace the transport client used by the backend."""
        self._client = client


@pytest.mark.asyncio
async def test_lsp_message_framing_round_trip() -> None:
    """Verify LSP message framing can be encoded and decoded."""
    payload: JSONDict = {"jsonrpc": "2.0", "id": 1, "method": "test", "params": {"a": 1}}
    encoded = encode_lsp_message(payload)

    reader = asyncio.StreamReader()
    reader.feed_data(encoded)
    reader.feed_eof()

    decoded = await read_lsp_message(reader)
    assert decoded == payload


@pytest.mark.asyncio
async def test_request_response_id_correlation() -> None:
    """Verify pending request futures resolve by matching response id."""
    client = LSPClientHarness()

    loop = asyncio.get_running_loop()
    future: asyncio.Future[JSONDict] = loop.create_future()
    client.add_pending_future(22, future)

    await client.route_message({"jsonrpc": "2.0", "id": 22, "result": {"ok": True}})
    result = await future
    assert result["result"] == {"ok": True}


@pytest.mark.asyncio
async def test_request_response_id_correlation_with_string_id() -> None:
    """Verify pending request futures resolve when server returns string numeric ids."""
    client = LSPClientHarness()

    loop = asyncio.get_running_loop()
    future: asyncio.Future[JSONDict] = loop.create_future()
    client.add_pending_future(23, future)

    await client.route_message({"jsonrpc": "2.0", "id": "23", "result": {"ok": True}})
    result = await future
    assert result["result"] == {"ok": True}


@pytest.mark.asyncio
async def test_notification_routing() -> None:
    """Verify notifications are dispatched to registered handlers."""
    client = LSPClientHarness()
    received: list[JSONDict] = []

    async def _handler(params: JSONDict) -> None:
        received.append(params)

    client.register_notification_handler("textDocument/publishDiagnostics", _handler)

    await client.route_message(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {"uri": "file:///tmp/a.py", "diagnostics": []},
        }
    )

    assert received == [{"uri": "file:///tmp/a.py", "diagnostics": []}]


def test_windows_uri_conversion_round_trip() -> None:
    """Verify URI/path conversion handles Windows drive-letter URIs."""
    uri = "file:///c:/repo/main.py"
    path = uri_to_path(uri)

    if os.name == "nt":
        assert path.endswith("repo\\main.py")
    else:
        assert path.endswith("c:/repo/main.py") or path.endswith("C:/repo/main.py")

    converted = path_to_uri(path)
    assert converted.lower().startswith("file:///")


@pytest.mark.asyncio
async def test_ensure_file_open_deduplicates(tmp_path: Path) -> None:
    """Verify repeated ensure_file_open only sends didOpen once per file."""
    sample = tmp_path / "sample.py"
    sample.write_text("x = 1\n", encoding="utf-8")

    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = PyrightClientHarness(config)
    fake_client = FakeLSPClient()
    backend.set_client(cast(LSPClient, fake_client))

    await backend.ensure_file_open(str(sample))
    await backend.ensure_file_open(str(sample))

    did_open_calls = [name for name, _ in fake_client.notifications if name == "textDocument/didOpen"]
    assert len(did_open_calls) == 1


@pytest.mark.asyncio
async def test_call_hierarchy_mapping_uses_incoming_and_outgoing_payloads(tmp_path: Path) -> None:
    """Verify call hierarchy request payloads are formed correctly."""
    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )

    backend = PyrightClientHarness(config)
    fake_client = FakeLSPClient(
        responses={
            "callHierarchy/incomingCalls": {
                "jsonrpc": "2.0",
                "id": 2,
                "result": [
                    {
                        "from": {
                            "name": "caller",
                            "kind": 12,
                            "uri": path_to_uri(str(tmp_path / "a.py")),
                            "range": {
                                "start": {"line": 1, "character": 0},
                                "end": {"line": 1, "character": 6},
                            },
                        }
                    }
                ],
            },
            "callHierarchy/outgoingCalls": {
                "jsonrpc": "2.0",
                "id": 3,
                "result": [
                    {
                        "to": {
                            "name": "callee",
                            "kind": 12,
                            "uri": path_to_uri(str(tmp_path / "b.py")),
                            "range": {
                                "start": {"line": 2, "character": 0},
                                "end": {"line": 2, "character": 6},
                            },
                        }
                    }
                ],
            },
        }
    )
    backend.set_client(cast(LSPClient, fake_client))

    item = CallHierarchyItem(
        name="target",
        kind="function",
        file_path=str(tmp_path / "c.py"),
        range=Range(start=Position(line=0, character=0), end=Position(line=0, character=6)),
    )

    incoming = await backend.get_incoming_calls(item)
    outgoing = await backend.get_outgoing_calls(item)

    assert incoming and incoming[0].name == "caller"
    assert outgoing and outgoing[0].name == "callee"


@pytest.mark.asyncio
async def test_document_symbol_mapping_returns_outline_items(tmp_path: Path) -> None:
    """Verify documentSymbol payloads map into hierarchical outline items."""
    sample = tmp_path / "sample.py"
    sample.write_text("def f():\n    pass\n", encoding="utf-8")

    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = PyrightClientHarness(config)
    fake_client = FakeLSPClient(
        responses={
            "textDocument/documentSymbol": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": [
                    {
                        "name": "f",
                        "kind": 12,
                        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 1, "character": 0}},
                        "selectionRange": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 5}},
                    }
                ],
            }
        }
    )
    backend.set_client(cast(LSPClient, fake_client))

    result = await backend.get_document_symbols(str(sample))

    assert len(result) == 1
    assert result[0].name == "f"


@pytest.mark.asyncio
async def test_completion_mapping_returns_items(tmp_path: Path) -> None:
    """Verify completion responses are mapped to completion models."""
    sample = tmp_path / "sample.py"
    sample.write_text("value.\n", encoding="utf-8")

    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = PyrightClientHarness(config)
    fake_client = FakeLSPClient(
        responses={
            "textDocument/completion": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "items": [
                        {
                            "label": "append",
                            "kind": 6,
                            "detail": "(value: object) -> None",
                            "insertText": "append",
                            "documentation": {"value": "Append an item."},
                        }
                    ]
                },
            }
        }
    )
    backend.set_client(cast(LSPClient, fake_client))

    result = await backend.get_completions(str(sample), 0, 6)

    assert len(result) == 1
    assert result[0].label == "append"


@pytest.mark.asyncio
async def test_signature_help_mapping_returns_active_signature(tmp_path: Path) -> None:
    """Verify signature help responses map to project models."""
    sample = tmp_path / "sample.py"
    sample.write_text("func(\n", encoding="utf-8")

    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = PyrightClientHarness(config)
    fake_client = FakeLSPClient(
        responses={
            "textDocument/signatureHelp": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "activeSignature": 0,
                    "activeParameter": 1,
                    "signatures": [
                        {
                            "label": "func(a: int, b: str)",
                            "documentation": {"value": "doc"},
                            "parameters": [
                                {"label": "a: int"},
                                {"label": "b: str"},
                            ],
                        }
                    ],
                },
            }
        }
    )
    backend.set_client(cast(LSPClient, fake_client))

    result = await backend.get_signature_help(str(sample), 0, 5)

    assert result is not None
    assert result.active_parameter == 1
    assert result.parameters[1].label == "b: str"


@pytest.mark.asyncio
async def test_workspace_symbol_mapping_returns_symbol_info(tmp_path: Path) -> None:
    """Verify workspace symbols are converted into SymbolInfo models."""
    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = PyrightClientHarness(config)
    fake_client = FakeLSPClient(
        responses={
            "workspace/symbol": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": [
                    {
                        "name": "Widget",
                        "kind": 5,
                        "containerName": "module",
                        "location": {
                            "uri": path_to_uri(str(tmp_path / "sample.py")),
                            "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 6}},
                        },
                    }
                ],
            }
        }
    )
    backend.set_client(cast(LSPClient, fake_client))

    result = await backend.workspace_symbol("Widget")

    assert len(result) == 1
    assert result[0].name == "Widget"


@pytest.mark.asyncio
async def test_implementation_mapping_returns_locations(tmp_path: Path) -> None:
    """Verify implementation responses reuse location mapping correctly."""
    sample = tmp_path / "sample.py"
    sample.write_text("pass\n", encoding="utf-8")

    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = PyrightClientHarness(config)
    fake_client = FakeLSPClient(
        responses={
            "textDocument/implementation": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": [
                    {
                        "uri": path_to_uri(str(sample)),
                        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 4}},
                    }
                ],
            }
        }
    )
    backend.set_client(cast(LSPClient, fake_client))

    result = await backend.get_implementation(str(sample), 0, 0)

    assert len(result) == 1
    assert result[0].file_path == str(sample.resolve())


def test_encode_message_has_valid_content_length() -> None:
    """Verify encoded messages include correct content length header."""
    payload: JSONDict = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    encoded = encode_lsp_message(payload)
    header, body = encoded.split(b"\r\n\r\n", maxsplit=1)

    header_text = header.decode("ascii")
    length_value = int(header_text.split(":", maxsplit=1)[1].strip())
    assert length_value == len(body)

    decoded_body = json.loads(body.decode("utf-8"))
    assert decoded_body == payload


@pytest.mark.asyncio
async def test_declaration_and_type_definition_mapping(tmp_path: Path) -> None:
    """Verify declaration and typeDefinition responses map into location models."""
    sample = tmp_path / "sample.py"
    sample.write_text("value = 1\n", encoding="utf-8")

    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = PyrightClientHarness(config)
    fake_client = FakeLSPClient(
        responses={
            "textDocument/declaration": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "uri": path_to_uri(str(sample)),
                    "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}},
                },
            },
            "textDocument/typeDefinition": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": [
                    {
                        "uri": path_to_uri(str(sample)),
                        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}},
                    }
                ],
            },
        }
    )
    backend.set_client(cast(LSPClient, fake_client))

    declarations = await backend.get_declaration(str(sample), 0, 0)
    type_definitions = await backend.get_type_definition(str(sample), 0, 0)

    assert len(declarations) == 1
    assert len(type_definitions) == 1


@pytest.mark.asyncio
async def test_document_highlights_and_prepare_rename_mapping(tmp_path: Path) -> None:
    """Verify document highlights and prepareRename payloads map correctly."""
    sample = tmp_path / "sample.py"
    sample.write_text("value = other\n", encoding="utf-8")

    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = PyrightClientHarness(config)
    fake_client = FakeLSPClient(
        responses={
            "textDocument/documentHighlight": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": [
                    {
                        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}},
                        "kind": 3,
                    }
                ],
            },
            "textDocument/prepareRename": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}},
                    "placeholder": "value",
                },
            },
        }
    )
    backend.set_client(cast(LSPClient, fake_client))

    highlights = await backend.get_document_highlights(str(sample), 0, 1)
    rename = await backend.prepare_rename(str(sample), 0, 1)

    assert len(highlights) == 1
    assert highlights[0].kind == "write"
    assert rename is not None
    assert rename.placeholder == "value"


@pytest.mark.asyncio
async def test_inlay_semantic_and_folding_mapping(tmp_path: Path) -> None:
    """Verify inlay hints, semantic tokens, and folding ranges map correctly."""
    sample = tmp_path / "sample.py"
    sample.write_text("def f(x):\n    return x\n", encoding="utf-8")

    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = PyrightClientHarness(config)
    fake_client = FakeLSPClient(
        responses={
            "textDocument/inlayHint": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": [
                    {
                        "position": {"line": 0, "character": 6},
                        "label": ": int",
                        "kind": 1,
                        "paddingLeft": True,
                        "paddingRight": False,
                    }
                ],
            },
            "textDocument/semanticTokens/full": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"data": [0, 0, 3, 12, 1]},
            },
            "textDocument/foldingRange": {
                "jsonrpc": "2.0",
                "id": 1,
                "result": [{"startLine": 0, "endLine": 1, "kind": "region"}],
            },
        }
    )
    backend.set_client(cast(LSPClient, fake_client))

    hints = await backend.get_inlay_hints(str(sample), 0, 0, 1, 0)
    tokens = await backend.get_semantic_tokens(str(sample))
    ranges = await backend.get_folding_ranges(str(sample))

    assert len(hints) == 1
    assert hints[0].kind == "type"
    assert len(tokens) == 1
    assert tokens[0].token_type == "function"
    assert len(ranges) == 1
    assert ranges[0].start_line == 0
