"""Unit tests for LSP transport and Pyright backend behavior."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient, path_to_uri, uri_to_path
from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import LspFeatureUnsupportedError, PyrightError, ToolInputError
from python_refactor_mcp.models import CallHierarchyItem, Position, Range, TypeHierarchyItem
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

    def pending_count(self) -> int:
        """Return the number of request futures still owned by the client."""
        return len(self._pending)

    def set_subprocess_manager(self, manager: Any) -> None:
        """Replace the subprocess manager with a narrow transport fake."""
        self._subprocess_mgr = manager


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


@pytest.mark.asyncio
async def test_request_write_failure_does_not_orphan_pending_future() -> None:
    """A transport failure before awaiting the response still releases request state."""
    client = LSPClientHarness()
    process = MagicMock()
    process.stdin = MagicMock()
    process.stdin.drain = AsyncMock(side_effect=BrokenPipeError("closed"))
    manager = MagicMock()
    manager.require_process.return_value = process
    client.set_subprocess_manager(manager)

    with pytest.raises(BrokenPipeError, match="closed"):
        await client.send_request("shutdown", {})

    assert client.pending_count() == 0


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


_OTHER_RANGE: dict[str, JSONValue] = {
    "start": {"line": 0, "character": 8},
    "end": {"line": 0, "character": 13},
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "character", "expected_placeholder"),
    [
        pytest.param(_OTHER_RANGE, 10, "other", id="bare-range"),
        pytest.param({"range": _OTHER_RANGE, "placeholder": "renamed"}, 10, "renamed", id="range-with-placeholder"),
        pytest.param({"defaultBehavior": True}, 10, "other", id="default-behavior-inside-word"),
        pytest.param({"defaultBehavior": True}, 13, "other", id="default-behavior-word-end"),
    ],
)
async def test_prepare_rename_maps_every_lsp_reply_shape(
    tmp_path: Path,
    result: JSONValue,
    character: int,
    expected_placeholder: str,
) -> None:
    """Verify each LSP PrepareRenameResult shape yields the identifier range."""
    backend, _, sample = _position_harness(
        tmp_path,
        {"textDocument/prepareRename": {"jsonrpc": "2.0", "id": 1, "result": result}},
    )

    rename = await backend.prepare_rename(str(sample), 0, character)

    assert rename is not None
    assert rename.range.start == Position(line=0, character=8)
    assert rename.range.end == Position(line=0, character=13)
    assert rename.placeholder == expected_placeholder


# "s = '<astral>' + other": the astral code point is 1 Python char but 2 UTF-16
# units, so ``other`` spans code points 10-15 and LSP characters 11-16.
_ASTRAL_LINE = "s = '\U0001f600' + other\n"
_ASTRAL_OTHER_RANGE: dict[str, JSONValue] = {
    "start": {"line": 0, "character": 11},
    "end": {"line": 0, "character": 16},
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "character"),
    [
        pytest.param({"defaultBehavior": True}, 13, id="default-behavior-inside-word"),
        pytest.param({"defaultBehavior": True}, 11, id="default-behavior-word-start"),
        pytest.param(_ASTRAL_OTHER_RANGE, 13, id="bare-range-placeholder-slice"),
    ],
)
async def test_prepare_rename_uses_utf16_columns_after_astral_character(
    tmp_path: Path,
    result: JSONValue,
    character: int,
) -> None:
    """Verify an astral character before the identifier keeps range and placeholder aligned."""
    backend, _, sample = _position_harness(
        tmp_path,
        {"textDocument/prepareRename": {"jsonrpc": "2.0", "id": 1, "result": result}},
    )
    sample.write_text(_ASTRAL_LINE, encoding="utf-8")

    rename = await backend.prepare_rename(str(sample), 0, character)

    assert rename is not None
    assert rename.range.start == Position(line=0, character=11)
    assert rename.range.end == Position(line=0, character=16)
    assert rename.placeholder == "other"


@pytest.mark.asyncio
async def test_prepare_rename_rejects_cursor_on_astral_character(tmp_path: Path) -> None:
    """Verify a cursor on the surrogate pair itself is not mistaken for an identifier."""
    backend, _, sample = _position_harness(
        tmp_path,
        {"textDocument/prepareRename": {"jsonrpc": "2.0", "id": 1, "result": {"defaultBehavior": True}}},
    )
    sample.write_text(_ASTRAL_LINE, encoding="utf-8")

    assert await backend.prepare_rename(str(sample), 0, 6) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "character"),
    [
        pytest.param(None, 10, id="null"),
        pytest.param({"defaultBehavior": False}, 10, id="default-behavior-false"),
        pytest.param({"defaultBehavior": True}, 6, id="default-behavior-off-identifier"),
        pytest.param({"unexpected": 1}, 10, id="unknown-dict"),
    ],
)
async def test_prepare_rename_rejects_non_renameable_replies(
    tmp_path: Path,
    result: JSONValue,
    character: int,
) -> None:
    """Verify null, rejected, and unrecognized prepareRename replies map to None."""
    backend, _, sample = _position_harness(
        tmp_path,
        {"textDocument/prepareRename": {"jsonrpc": "2.0", "id": 1, "result": result}},
    )

    assert await backend.prepare_rename(str(sample), 0, character) is None


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


def _position_harness(
    tmp_path: Path, responses: dict[str, JSONDict | None]
) -> tuple[PyrightClientHarness, FakeLSPClient, Path]:
    """Build a Pyright harness with a fake transport seeded with ``responses``."""
    sample = tmp_path / "sample.py"
    # Four lines (0-3), each wide enough that the coordinates exercised by the
    # envelope-shape tests below (e.g. line 3 / char 7) stay in range.
    sample.write_text(
        "value = other\nalpha = beta\ngamma = delta\nepsilon = zeta\n",
        encoding="utf-8",
    )

    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = PyrightClientHarness(config)
    fake_client = FakeLSPClient(responses=responses)
    backend.set_client(cast(LSPClient, fake_client))
    return backend, fake_client, sample


@pytest.mark.asyncio
async def test_position_request_definition_builds_text_document_and_position(tmp_path: Path) -> None:
    """_position_request sends the canonical textDocument+position envelope with no extras."""
    backend, fake_client, sample = _position_harness(
        tmp_path,
        {"textDocument/definition": {"jsonrpc": "2.0", "id": 1, "result": []}},
    )

    await backend.get_definition(str(sample), 3, 7)

    recorded = [params for method, params in fake_client.requests if method == "textDocument/definition"]
    assert len(recorded) == 1
    assert recorded[0] == {
        "textDocument": {"uri": path_to_uri(str(sample.resolve()))},
        "position": {"line": 3, "character": 7},
    }
    assert "context" not in recorded[0]


@pytest.mark.asyncio
async def test_position_request_hover_builds_text_document_and_position(tmp_path: Path) -> None:
    """_position_request forms a hover payload with exactly textDocument and position keys."""
    backend, fake_client, sample = _position_harness(
        tmp_path,
        {"textDocument/hover": {"jsonrpc": "2.0", "id": 1, "result": None}},
    )

    await backend.get_hover(str(sample), 1, 4)

    recorded = [params for method, params in fake_client.requests if method == "textDocument/hover"]
    assert len(recorded) == 1
    assert recorded[0] == {
        "textDocument": {"uri": path_to_uri(str(sample.resolve()))},
        "position": {"line": 1, "character": 4},
    }


@pytest.mark.asyncio
async def test_position_request_references_merges_extra_params_without_clobber(tmp_path: Path) -> None:
    """_position_request merges extra_params (context) alongside the envelope keys."""
    backend, fake_client, sample = _position_harness(
        tmp_path,
        {"textDocument/references": {"jsonrpc": "2.0", "id": 1, "result": []}},
    )

    await backend.get_references(str(sample), 2, 5, include_declaration=True)

    recorded = [params for method, params in fake_client.requests if method == "textDocument/references"]
    assert len(recorded) == 1
    assert recorded[0] == {
        "textDocument": {"uri": path_to_uri(str(sample.resolve()))},
        "position": {"line": 2, "character": 5},
        "context": {"includeDeclaration": True},
    }


@pytest.mark.asyncio
async def test_position_request_rejects_reserved_extra_params(tmp_path: Path) -> None:
    """Future callers cannot replace the canonical document or position envelope."""
    backend, fake_client, sample = _position_harness(tmp_path, {})

    with pytest.raises(ValueError, match="reserved LSP envelope keys: position, textDocument"):
        await backend._position_request(
            "textDocument/references",
            str(sample.resolve()),
            0,
            0,
            extra_params={
                "textDocument": {"uri": "file:///wrong.py"},
                "position": {"line": 99, "character": 99},
            },
        )

    assert fake_client.requests == []


@pytest.mark.asyncio
async def test_position_request_opens_file_before_request(tmp_path: Path) -> None:
    """_position_request opens the document (didOpen) before issuing the request."""
    backend, fake_client, sample = _position_harness(
        tmp_path,
        {"textDocument/definition": {"jsonrpc": "2.0", "id": 1, "result": []}},
    )

    await backend.get_definition(str(sample), 0, 0)

    did_open = [name for name, _ in fake_client.notifications if name == "textDocument/didOpen"]
    request_methods = [name for name, _ in fake_client.requests]
    assert did_open == ["textDocument/didOpen"]
    assert "textDocument/definition" in request_methods


@pytest.mark.asyncio
async def test_position_request_declaration_fallback_to_definition_preserved(tmp_path: Path) -> None:
    """get_declaration still falls back to get_definition on an unhandled-method error."""
    sample_uri = path_to_uri(str((tmp_path / "sample.py").resolve()))
    backend, fake_client, sample = _position_harness(
        tmp_path,
        {
            "textDocument/declaration": {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32601, "message": "Unhandled method textDocument/declaration"},
            },
            "textDocument/definition": {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "uri": sample_uri,
                    "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 5}},
                },
            },
        },
    )

    locations = await backend.get_declaration(str(sample), 0, 0)

    requested = [method for method, _ in fake_client.requests]
    assert "textDocument/declaration" in requested
    assert "textDocument/definition" in requested
    assert len(locations) == 1


@pytest.mark.asyncio
async def test_position_request_rejects_line_beyond_eof(tmp_path: Path) -> None:
    """An out-of-range line raises a structured error instead of a silent empty result."""
    backend, fake_client, sample = _position_harness(
        tmp_path,
        {"textDocument/references": {"jsonrpc": "2.0", "id": 1, "result": []}},
    )

    with pytest.raises(ToolInputError, match=r"^line 999999 is out of range"):
        await backend.get_references(str(sample), 999_999, 0, include_declaration=True)

    # The bad coordinate must short-circuit before any LSP round-trip.
    requested = [method for method, _ in fake_client.requests]
    assert "textDocument/references" not in requested


@pytest.mark.asyncio
async def test_position_request_rejects_character_beyond_line_length(tmp_path: Path) -> None:
    """A character past the line's end raises a structured error, not a silent empty result."""
    backend, fake_client, sample = _position_harness(
        tmp_path,
        {"textDocument/definition": {"jsonrpc": "2.0", "id": 1, "result": []}},
    )

    # Line 0 is "value = other" (13 chars); character 99 is past its end.
    with pytest.raises(ToolInputError, match=r"^character 99 is out of range"):
        await backend.get_definition(str(sample), 0, 99)

    requested = [method for method, _ in fake_client.requests]
    assert "textDocument/definition" not in requested


@pytest.mark.asyncio
async def test_position_request_bounds_character_by_utf16_line_length(tmp_path: Path) -> None:
    """The end-of-line bound counts UTF-16 units, so an astral character widens it by two."""
    backend, fake_client, sample = _position_harness(
        tmp_path,
        {"textDocument/definition": {"jsonrpc": "2.0", "id": 1, "result": []}},
    )
    # _ASTRAL_LINE is 15 code points but 16 UTF-16 units; 16 is the end of ``other``.
    sample.write_text(_ASTRAL_LINE, encoding="utf-8")

    assert await backend.get_definition(str(sample), 0, 16) == []
    requested = [method for method, _ in fake_client.requests]
    assert "textDocument/definition" in requested

    # Match the message, not the class: the error type is owned by a sibling change.
    with pytest.raises(Exception, match=r"^character 17 is out of range: line 0 has 16 UTF-16 code unit"):
        await backend.get_definition(str(sample), 0, 17)


@pytest.mark.asyncio
async def test_position_request_rejects_negative_coordinate(tmp_path: Path) -> None:
    """A negative line or character raises a structured error."""
    backend, fake_client, sample = _position_harness(
        tmp_path,
        {"textDocument/definition": {"jsonrpc": "2.0", "id": 1, "result": []}},
    )

    with pytest.raises(ToolInputError, match=r"^line must be non-negative"):
        await backend.get_definition(str(sample), -1, 0)
    with pytest.raises(ToolInputError, match=r"^character must be non-negative"):
        await backend.get_definition(str(sample), 0, -1)

    requested = [method for method, _ in fake_client.requests]
    assert "textDocument/definition" not in requested


@pytest.mark.asyncio
async def test_position_request_rejects_nonexistent_file_as_input_error(tmp_path: Path) -> None:
    """A nonexistent file_path is caller input: ToolInputError naming file_path, no didOpen."""
    backend, fake_client, _sample = _position_harness(
        tmp_path,
        {"textDocument/definition": {"jsonrpc": "2.0", "id": 1, "result": []}},
    )
    missing = tmp_path / "does_not_exist.py"

    with pytest.raises(ToolInputError, match=r"^file_path does not exist") as excinfo:
        await backend.get_definition(str(missing), 0, 0)

    assert not isinstance(excinfo.value, PyrightError)
    assert fake_client.notifications == []
    assert fake_client.requests == []


@pytest.mark.asyncio
async def test_position_request_unreadable_file_stays_backend_error(tmp_path: Path) -> None:
    """An existing but undecodable file is a backend failure and keeps the PyrightError shape."""
    backend, fake_client, _sample = _position_harness(
        tmp_path,
        {"textDocument/definition": {"jsonrpc": "2.0", "id": 1, "result": []}},
    )
    undecodable = tmp_path / "not_utf8.py"
    undecodable.write_bytes(b"name = '\xff\xfe'\n")

    with pytest.raises(PyrightError, match="Cannot read file"):
        await backend.get_definition(str(undecodable), 0, 0)

    assert fake_client.requests == []


@pytest.mark.asyncio
async def test_position_request_allows_in_range_zero_result(tmp_path: Path) -> None:
    """A valid in-range coordinate with no results still returns empty (happy path preserved)."""
    backend, fake_client, sample = _position_harness(
        tmp_path,
        {"textDocument/references": {"jsonrpc": "2.0", "id": 1, "result": []}},
    )

    # Line 3 "epsilon = zeta" is valid; character 14 == end-of-line is allowed.
    references = await backend.get_references(str(sample), 3, 14, include_declaration=True)

    assert references == []
    requested = [method for method, _ in fake_client.requests]
    assert "textDocument/references" in requested


@pytest.mark.asyncio
async def test_warm_position_request_reads_source_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Warm validation reuses refresh content instead of reading the file twice."""
    backend, _fake_client, sample = _position_harness(
        tmp_path,
        {"textDocument/definition": {"jsonrpc": "2.0", "id": 1, "result": []}},
    )
    await backend.ensure_file_open(str(sample))
    original_read_text = Path.read_text
    reads: list[Path] = []

    def _tracked_read_text(path: Path, *args: object, **kwargs: object) -> str:
        reads.append(path)
        return original_read_text(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", _tracked_read_text)

    await backend.get_definition(str(sample), 0, 0)

    assert reads == [sample.resolve()]


@pytest.mark.asyncio
async def test_warm_position_request_refreshes_cached_source(tmp_path: Path) -> None:
    """External source changes update both Pyright and position validation."""
    backend, fake_client, sample = _position_harness(
        tmp_path,
        {"textDocument/definition": {"jsonrpc": "2.0", "id": 1, "result": []}},
    )
    await backend.ensure_file_open(str(sample))
    sample.write_text(sample.read_text(encoding="utf-8") + "new_line = 1\n", encoding="utf-8")

    await backend.get_definition(str(sample), 4, 0)

    methods = [method for method, _ in fake_client.requests]
    assert "textDocument/definition" in methods
    assert any("didChange" in notification[0] for notification in fake_client.notifications)


# ── Unsupported LSP features (selectionRange / inlayHint / semanticTokens) ──


class StartableHarness(PyrightLSPClient):
    """Pyright harness whose ``start``/restart handshake runs on fake transports."""

    def __init__(self, config: ServerConfig, responses: dict[str, JSONDict | None]) -> None:
        self._fake_responses = responses
        self.fakes: list[FakeLSPClient] = []
        super().__init__(config)

    def _make_client(self) -> LSPClient:
        fake = FakeLSPClient(responses=self._fake_responses)
        self.fakes.append(fake)
        return cast(LSPClient, fake)

    def reseed(self, responses: dict[str, JSONDict | None]) -> None:
        """Replace the responses future fake transports are built with."""
        self._fake_responses = responses

    async def restart(self) -> None:
        """Expose the crash-restart path for tests."""
        await self._restart()


def _initialize_reply(capabilities: JSONDict) -> JSONDict:
    return {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": capabilities}}


def _startable_harness(
    tmp_path: Path, responses: dict[str, JSONDict | None]
) -> tuple[StartableHarness, Path]:
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
    return StartableHarness(config, responses), sample


def _type_hierarchy_item(path: str) -> TypeHierarchyItem:
    """Build a minimal type hierarchy item for supertypes/subtypes requests."""
    origin = Position(line=0, character=0)
    return TypeHierarchyItem(name="Sample", kind="class", file_path=path, range=Range(start=origin, end=origin))


_UNSUPPORTED_FEATURES = [
    pytest.param(
        "selectionRangeProvider",
        "textDocument/selectionRange",
        lambda backend, path: backend.get_selection_range(path, [Position(line=0, character=0)]),
        id="selection-range",
    ),
    pytest.param(
        "inlayHintProvider",
        "textDocument/inlayHint",
        lambda backend, path: backend.get_inlay_hints(path, 0, 0, 1, 0),
        id="inlay-hint",
    ),
    pytest.param(
        "semanticTokensProvider",
        "textDocument/semanticTokens/full",
        lambda backend, path: backend.get_semantic_tokens(path),
        id="semantic-tokens",
    ),
    pytest.param(
        "implementationProvider",
        "textDocument/implementation",
        lambda backend, path: backend.get_implementation(path, 0, 0),
        id="implementation",
    ),
    pytest.param(
        "typeHierarchyProvider",
        "textDocument/prepareTypeHierarchy",
        lambda backend, path: backend.prepare_type_hierarchy(path, 0, 0),
        id="prepare-type-hierarchy",
    ),
    pytest.param(
        "typeHierarchyProvider",
        "typeHierarchy/supertypes",
        lambda backend, path: backend.get_supertypes(_type_hierarchy_item(path)),
        id="supertypes",
    ),
    pytest.param(
        "typeHierarchyProvider",
        "typeHierarchy/subtypes",
        lambda backend, path: backend.get_subtypes(_type_hierarchy_item(path)),
        id="subtypes",
    ),
    pytest.param(
        "typeDefinitionProvider",
        "textDocument/typeDefinition",
        lambda backend, path: backend.get_type_definition(path, 0, 0),
        id="type-definition",
    ),
    pytest.param(
        "foldingRangeProvider",
        "textDocument/foldingRange",
        lambda backend, path: backend.get_folding_ranges(path),
        id="folding-range",
    ),
]


@pytest.mark.asyncio
async def test_start_and_restart_record_server_capabilities(tmp_path: Path) -> None:
    """Both handshakes store the advertised capabilities that gate feature calls."""
    backend, sample = _startable_harness(
        tmp_path,
        {"initialize": _initialize_reply({"hoverProvider": True})},
    )

    await backend.start()
    with pytest.raises(LspFeatureUnsupportedError):
        await backend.get_inlay_hints(str(sample), 0, 0, 1, 0)

    backend.reseed(
        {
            "initialize": _initialize_reply({"inlayHintProvider": True}),
            "textDocument/inlayHint": {"jsonrpc": "2.0", "id": 1, "result": []},
        }
    )
    await backend.restart()

    assert await backend.get_inlay_hints(str(sample), 0, 0, 1, 0) == []
    restarted = backend.fakes[-1]
    assert [method for method, _ in restarted.requests] == ["initialize", "textDocument/inlayHint"]
    assert [method for method, _ in restarted.notifications][:2] == [
        "initialized",
        "workspace/didChangeConfiguration",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider_key", "method", "call"), _UNSUPPORTED_FEATURES)
async def test_unadvertised_capability_raises_without_sending_request(
    tmp_path: Path,
    provider_key: str,
    method: str,
    call: Any,
) -> None:
    """A capability Pyright did not advertise fails fast with LSP_UNSUPPORTED."""
    backend, sample = _startable_harness(
        tmp_path,
        {"initialize": _initialize_reply({"hoverProvider": True})},
    )
    await backend.start()

    with pytest.raises(LspFeatureUnsupportedError, match=provider_key) as raised:
        await call(backend, str(sample))

    assert raised.value.code == "LSP_UNSUPPORTED"
    assert method not in [sent for sent, _ in backend.fakes[-1].requests]


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider_key", "method", "call"), _UNSUPPORTED_FEATURES)
async def test_unhandled_method_reply_raises_unsupported(
    tmp_path: Path,
    provider_key: str,
    method: str,
    call: Any,
) -> None:
    """A -32601 Unhandled method reply raises instead of returning an empty list."""
    _ = provider_key
    backend, _, sample = _position_harness(
        tmp_path,
        {
            method: {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32601, "message": f"Unhandled method {method}"},
            }
        },
    )

    with pytest.raises(LspFeatureUnsupportedError, match="unhandled by Pyright"):
        await call(backend, str(sample))


# ── Request timeout on the post-restart retry ──


class DiesThenHangsClient(FakeLSPClient):
    """Transport whose first request dies with the process; the retry never completes."""

    def __init__(self) -> None:
        super().__init__()
        self.alive = True
        self.send_count = 0

    def is_alive(self) -> bool:
        return self.alive

    async def send_request(self, method: str, params: dict[str, JSONValue]) -> JSONDict:
        self.requests.append((method, params))
        self.send_count += 1
        if self.send_count == 1:
            self.alive = False
            raise PyrightError("Pyright process exited during request")
        await asyncio.Event().wait()
        raise AssertionError("unreachable: the retry must be cancelled by its timeout")


class RetryTimeoutHarness(PyrightClientHarness):
    """Harness with a no-op restart and a short request timeout."""

    def __init__(self, config: ServerConfig) -> None:
        super().__init__(config)
        self._request_timeout_seconds = 0.2
        self.restart_count = 0

    async def _restart(self) -> None:
        self.restart_count += 1

    async def request(self, method: str, params: dict[str, JSONValue]) -> JSONDict:
        """Expose the timeout/restart request path for tests."""
        return await self._request(method, params)


@pytest.mark.asyncio
async def test_post_restart_retry_timeout_raises_pyright_error(tmp_path: Path) -> None:
    """A retry that hangs after a crash-restart raises PyrightError, not a raw TimeoutError."""
    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = RetryTimeoutHarness(config)
    client = DiesThenHangsClient()
    backend.set_client(cast(LSPClient, client))

    with pytest.raises(PyrightError, match=r"^textDocument/hover request timed out after 0\.2s$") as raised:
        await backend.request("textDocument/hover", {})

    assert isinstance(raised.value.__cause__, TimeoutError)
    assert backend.restart_count == 1
    assert client.send_count == 2
