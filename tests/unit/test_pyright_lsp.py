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
