"""Generic async JSON-RPC client for LSP subprocesses."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from itertools import count

from python_refactor_mcp.errors import PyrightError
from python_refactor_mcp.util.subprocess_mgr import SubprocessManager

JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONDict = dict[str, JSONValue]
NotificationHandler = Callable[[JSONDict], Awaitable[None]]

_CONTENT_LENGTH = "content-length"
_LOGGER = logging.getLogger(__name__)


def _normalize_response_id(value: JSONValue) -> int | None:
    """Normalize JSON-RPC response ids to integer keys when possible."""
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def encode_lsp_message(payload: JSONDict) -> bytes:
    """Encode a JSON-RPC payload into an LSP-framed byte sequence."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


async def read_lsp_message(stream: asyncio.StreamReader) -> JSONDict:
    """Read a single LSP message from a stream reader."""
    headers: dict[str, str] = {}

    while True:
        raw_line = await stream.readline()
        if raw_line == b"":
            raise PyrightError("LSP stream closed while reading headers.")

        line = raw_line.decode("ascii", errors="strict").strip()
        if not line:
            break

        if ":" not in line:
            raise PyrightError(f"Invalid LSP header line: {line}")

        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()

    length_value = headers.get(_CONTENT_LENGTH)
    if length_value is None:
        raise PyrightError("Missing Content-Length header in LSP message.")

    try:
        content_length = int(length_value)
    except ValueError as exc:
        raise PyrightError(f"Invalid Content-Length value: {length_value}") from exc

    body = await stream.readexactly(content_length)
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PyrightError("Failed to decode LSP JSON payload.") from exc

    if not isinstance(decoded, dict):
        raise PyrightError("Expected JSON object payload from LSP stream.")

    message: JSONDict = decoded
    return message


class LSPClient:
    """Async LSP client that manages JSON-RPC state over subprocess transport."""

    def __init__(self) -> None:
        """Initialize the client with no running subprocess."""
        self._subprocess_mgr = SubprocessManager()
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()
        self._id_counter = count(1)
        self._pending: dict[int, asyncio.Future[JSONDict]] = {}
        self._notification_handlers: dict[str, NotificationHandler] = {}

    def register_notification_handler(self, method: str, handler: NotificationHandler) -> None:
        """Register an async callback for an LSP notification method."""
        self._notification_handlers[method] = handler

    async def start(self, command: list[str]) -> None:
        """Start the LSP subprocess and launch reader tasks."""
        process = await self._subprocess_mgr.start(command)

        assert process.stdout is not None
        assert process.stderr is not None

        self._reader_task = asyncio.create_task(self._reader_loop(process.stdout))
        self._stderr_task = asyncio.create_task(self._stderr_loop(process.stderr))

    async def send_request(self, method: str, params: dict[str, JSONValue]) -> JSONDict:
        """Send a JSON-RPC request and await its full response payload."""
        process = self._subprocess_mgr.require_process()
        if process.stdin is None:
            raise PyrightError("LSP subprocess stdin is unavailable.")

        request_id = next(self._id_counter)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[JSONDict] = loop.create_future()
        self._pending[request_id] = future

        payload: JSONDict = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        async with self._write_lock:
            process.stdin.write(encode_lsp_message(payload))
            await process.stdin.drain()

        try:
            response = await future
            return response
        finally:
            self._pending.pop(request_id, None)

    async def send_notification(self, method: str, params: dict[str, JSONValue]) -> None:
        """Send a JSON-RPC notification without waiting for a response."""
        process = self._subprocess_mgr.require_process()
        if process.stdin is None:
            raise PyrightError("LSP subprocess stdin is unavailable.")

        payload: JSONDict = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        async with self._write_lock:
            process.stdin.write(encode_lsp_message(payload))
            await process.stdin.drain()

    async def shutdown(self) -> None:
        """Shutdown the LSP subprocess and clean up all background tasks."""
        if self._subprocess_mgr.process is None:
            return

        try:
            await asyncio.wait_for(self.send_request("shutdown", {}), timeout=5.0)
        except Exception:
            _LOGGER.debug("Failed to send shutdown request to LSP process.", exc_info=True)

        try:
            await self.send_notification("exit", {})
        except Exception:
            _LOGGER.debug("Failed to send exit notification to LSP process.", exc_info=True)

        # Fail all pending requests before killing the process.
        for request_id, future in list(self._pending.items()):
            if not future.done():
                future.set_exception(PyrightError(f"LSP shutdown interrupted request id={request_id}"))
        self._pending.clear()

        await self._subprocess_mgr.shutdown()
        await SubprocessManager.cancel_task(self._reader_task)
        await SubprocessManager.cancel_task(self._stderr_task)

        self._reader_task = None
        self._stderr_task = None

    # ── Internal message routing ──────────────────────────────────────

    async def _reader_loop(self, stream: asyncio.StreamReader) -> None:
        """Read and route messages from the LSP server stdout stream."""
        try:
            while True:
                message = await read_lsp_message(stream)
                await self._route_message(message)
        except asyncio.IncompleteReadError:
            self._fail_pending(PyrightError("LSP stream closed unexpectedly."))
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.debug("LSP reader loop failed.", exc_info=True)
            self._fail_pending(PyrightError("LSP reader loop failed."))

    async def _stderr_loop(self, stream: asyncio.StreamReader) -> None:
        """Drain stderr so the child process cannot block on filled buffers."""
        try:
            while True:
                line = await stream.readline()
                if line == b"":
                    return
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    _LOGGER.debug("LSP stderr: %s", text)
        except asyncio.CancelledError:
            raise

    async def _respond(self, request_id: int | str, result: JSONValue = None) -> None:
        """Send a JSON-RPC response for a server-initiated request."""
        process = self._subprocess_mgr.process
        if process is None or process.stdin is None:
            return
        payload: JSONDict = {"jsonrpc": "2.0", "id": request_id, "result": result}
        async with self._write_lock:
            process.stdin.write(encode_lsp_message(payload))
            await process.stdin.drain()

    async def _route_message(self, message: JSONDict) -> None:
        """Dispatch a received message to a pending request or notification handler."""
        method_value = message.get("method")
        id_value = message.get("id")

        # Server-initiated request: has both id and method.  Respond with empty result.
        if isinstance(method_value, str) and id_value is not None:
            request_id = _normalize_response_id(id_value)
            if request_id is not None and request_id not in self._pending:
                _LOGGER.debug("Responding to server request: %s (id=%s)", method_value, id_value)
                await self._respond(id_value, result=None)  # type: ignore[arg-type]
                return

        request_id = _normalize_response_id(id_value)
        if request_id is not None:
            future = self._pending.pop(request_id, None)
            if future is not None and not future.done():
                future.set_result(message)
            return

        if isinstance(method_value, str):
            handler = self._notification_handlers.get(method_value)
            if handler is None:
                return
            params_value = message.get("params")
            params: JSONDict = params_value if isinstance(params_value, dict) else {}
            await handler(params)

    def _fail_pending(self, exc: Exception) -> None:
        """Fail all pending requests with the supplied exception."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()
