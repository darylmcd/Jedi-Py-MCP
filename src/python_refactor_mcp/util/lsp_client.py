"""Generic async JSON-RPC client for LSP subprocesses."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from itertools import count

from python_refactor_mcp.errors import PyrightError

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
	"""Async LSP client that manages subprocess transport and JSON-RPC state."""

	def __init__(self) -> None:
		"""Initialize the client with no running subprocess."""
		self._process: asyncio.subprocess.Process | None = None
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
		if self._process is not None:
			raise PyrightError("LSP subprocess is already running.")
		if not command:
			raise PyrightError("LSP command cannot be empty.")

		self._process = await asyncio.create_subprocess_exec(
			*command,
			stdin=asyncio.subprocess.PIPE,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
		)

		if self._process.stdout is None or self._process.stdin is None or self._process.stderr is None:
			raise PyrightError("Failed to acquire stdio pipes for LSP subprocess.")

		self._reader_task = asyncio.create_task(self._reader_loop(self._process.stdout))
		self._stderr_task = asyncio.create_task(self._stderr_loop(self._process.stderr))

	async def send_request(self, method: str, params: dict[str, JSONValue]) -> JSONDict:
		"""Send a JSON-RPC request and await its full response payload."""
		process = self._require_process()
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
		process = self._require_process()
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
		process = self._process
		if process is None:
			return

		try:
			await self.send_request("shutdown", {})
		except Exception:
			_LOGGER.debug("Failed to send shutdown request to LSP process.", exc_info=True)

		try:
			await self.send_notification("exit", {})
		except Exception:
			_LOGGER.debug("Failed to send exit notification to LSP process.", exc_info=True)

		if process.stdin is not None:
			process.stdin.close()

		try:
			await asyncio.wait_for(process.wait(), timeout=3)
		except TimeoutError:
			process.terminate()
			try:
				await asyncio.wait_for(process.wait(), timeout=3)
			except TimeoutError:
				process.kill()
				await process.wait()

		await self._cancel_task(self._reader_task)
		await self._cancel_task(self._stderr_task)

		for request_id, future in list(self._pending.items()):
			if not future.done():
				future.set_exception(PyrightError(f"LSP shutdown interrupted request id={request_id}"))
		self._pending.clear()

		self._reader_task = None
		self._stderr_task = None
		self._process = None

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

	async def _route_message(self, message: JSONDict) -> None:
		"""Dispatch a received message to a pending request or notification handler."""
		method_value = message.get("method")
		id_value = message.get("id")
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

	def _require_process(self) -> asyncio.subprocess.Process:
		"""Return the running subprocess or raise a backend error."""
		if self._process is None:
			raise PyrightError("LSP subprocess has not been started.")
		return self._process

	@staticmethod
	async def _cancel_task(task: asyncio.Task[None] | None) -> None:
		"""Cancel and await a background task if it exists."""
		if task is None:
			return
		task.cancel()
		try:
			await task
		except asyncio.CancelledError:
			return
