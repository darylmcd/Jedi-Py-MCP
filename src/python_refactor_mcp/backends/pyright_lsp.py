"""Pyright language server backend over async JSON-RPC/LSP transport."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import cast

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import LspFeatureUnsupportedError, PyrightError, ToolInputError
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
    convert_diagnostics,
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

def _sorted_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    return sorted(
        diagnostics,
        key=lambda item: (
            item.file_path,
            item.range.start.line,
            item.range.start.character,
        ),
    )


def stamp_of(absolute_path: str) -> tuple[int, int]:
    """Return the change stamp ``(mtime_ns, size)`` of a file; raises ``OSError`` when it is gone."""
    stat = os.stat(absolute_path)
    return stat.st_mtime_ns, stat.st_size


def _utf16_units(character: str) -> int:
    """Return how many UTF-16 code units encode ``character`` (2 for astral code points)."""
    return 2 if ord(character) > 0xFFFF else 1


def _utf16_to_code_point_index(text: str, utf16_offset: int) -> int:
    """Map an LSP UTF-16 ``character`` offset on ``text`` to a Python string index.

    An offset inside a surrogate pair maps to the index of that code point. An
    offset past the end of ``text`` keeps its excess, so callers range-checking
    the result still see it as out of bounds.
    """
    if utf16_offset <= 0:
        return utf16_offset
    units = 0
    for index, character in enumerate(text):
        width = _utf16_units(character)
        if units + width > utf16_offset:
            return index
        units += width
        if units == utf16_offset:
            return index + 1
    return len(text) + (utf16_offset - units)


def _code_point_to_utf16_offset(text: str, index: int) -> int:
    """Map a Python string index on ``text`` to an LSP UTF-16 ``character`` offset."""
    if index <= 0:
        return index
    prefix = text[:index]
    return sum(_utf16_units(character) for character in prefix) + (index - len(prefix))


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
        self._file_contents: dict[str, str] = {}
        # ``(mtime_ns, size)`` taken BEFORE the text it describes was read, so a write
        # landing between the read and the stat shows up as a stale stamp, never a lost edit.
        self._file_stamps: dict[str, tuple[int, int]] = {}
        self._document_lock = asyncio.Lock()
        self._restart_lock = asyncio.Lock()
        self._session_invalid = False
        # Terminal: set by ``shutdown``. A closed backend never starts another process.
        self._closed = False
        self._startup_command: list[str] | None = None
        self._server_capabilities: JSONDict | None = None

    @property
    def workspace_root(self) -> Path:
        """Workspace root this client serves."""
        return self._config.workspace_root

    @property
    def is_running(self) -> bool:
        """Whether the Pyright language-server subprocess is alive.

        Cheap and non-blocking: checks the process and transport reader state.
        """
        return not self._closed and not self._session_invalid and self._client.is_alive()

    # ── LSP transport ─────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        params: dict[str, JSONValue],
        *,
        prepare: Callable[[LSPClient], Awaitable[None]] | None = None,
    ) -> JSONDict:
        """Send an LSP request with a bounded timeout and auto-restart on crash."""
        client = await self._ensure_healthy()
        timeout_message = f"{method} request timed out after {self._request_timeout_seconds:.1f}s"

        async def attempt(transport: LSPClient) -> JSONDict:
            if prepare is not None:
                await prepare(transport)
                if transport is not self._client:
                    raise PyrightError("Pyright session changed while preparing the request.")
            return await transport.send_request(method, params)

        async def bounded_attempt(transport: LSPClient) -> JSONDict:
            try:
                return await asyncio.wait_for(
                    attempt(transport),
                    timeout=self._request_timeout_seconds,
                )
            except TimeoutError as exc:
                raise PyrightError(timeout_message) from exc

        async with timed(_LOGGER, f"pyright.{method}"):
            try:
                return await bounded_attempt(client)
            except (BrokenPipeError, ConnectionResetError):
                replacement = await self._ensure_healthy(disconnected=client)
            except PyrightError as exc:
                if isinstance(exc.__cause__, TimeoutError) or (client is self._client and self.is_running):
                    raise
                replacement = await self._ensure_healthy()
            try:
                return await bounded_attempt(replacement)
            except (BrokenPipeError, ConnectionResetError) as exc:
                raise PyrightError("Pyright request transport disconnected.") from exc

    async def _ensure_healthy(self, *, disconnected: LSPClient | None = None) -> LSPClient:
        """Return the initialized transport, restarting if it has crashed."""
        async with self._restart_lock:
            self._require_open()
            if self._client is disconnected or not self.is_running:
                _LOGGER.warning("Pyright process detected as dead, attempting restart")
                await self._restart()
            return self._client

    async def _restart(self) -> None:
        """Restart the Pyright process using the stored startup command.

        Refuses on a closed backend, and re-checks after the new process started: a
        ``shutdown`` that began meanwhile waits for the restart lock, so this method
        never leaves a live process behind a closed backend.
        """
        self._require_open()
        if self._startup_command is None:
            raise PyrightError("Cannot restart Pyright: no startup command recorded")
        async with self._document_lock:
            self._session_invalid = True
            try:
                await self._client.shutdown()
            except Exception as exc:
                raise PyrightError("Could not stop the previous Pyright language server.") from exc
            self._clear_documents()
            self._client = self._make_client()
            try:
                await self._client.start(self._startup_command)
                await self._initialize_session()
                self._require_open()
            except (Exception, asyncio.CancelledError) as exc:
                try:
                    await self._client.shutdown()
                except Exception:
                    _LOGGER.warning("Could not clean up failed Pyright restart.", exc_info=True)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise PyrightError("Could not restart the Pyright language server.") from exc
            self._session_invalid = False
            _LOGGER.info("Pyright process restarted successfully")

    def _make_client(self) -> LSPClient:
        """Create a fresh LSP transport client.

        Diagnostics are pulled with ``textDocument/diagnostic``; the server's
        ``publishDiagnostics`` pushes are ignored.
        """
        return LSPClient()

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
        params = cast("dict[str, JSONValue]", {
            "processId": None,
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "publishDiagnostics": {"relatedInformation": True, "versionSupport": True},
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
        })
        return params

    async def _initialize_session(self) -> None:
        """Run the LSP initialize handshake on the current transport.

        Records the server's advertised ``capabilities`` so feature requests the
        running Pyright does not implement fail explicitly instead of silently.
        """
        self._server_capabilities = None
        response = await asyncio.wait_for(
            self._client.send_request("initialize", self._build_initialize_params()),
            timeout=15,
        )
        if "error" in response:
            raise PyrightError(f"Pyright initialize failed: {response['error']}")
        result = response.get("result")
        if isinstance(result, dict):
            capabilities = result.get("capabilities")
            if isinstance(capabilities, dict):
                self._server_capabilities = capabilities
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

    def _require_capability(self, provider_key: str, method: str) -> None:
        """Raise when the recorded server capabilities do not advertise ``provider_key``.

        Skipped when no capabilities were recorded (session not initialized by
        ``start``/restart, or a server that omitted them).
        """
        if self._server_capabilities is None:
            return
        if not self._server_capabilities.get(provider_key):
            raise LspFeatureUnsupportedError(
                f"Pyright does not advertise {provider_key}; {method} is unsupported"
            )

    async def start(self) -> None:
        """Start the Pyright language server and initialize the LSP session.

        Refuses a backend that :meth:`shutdown` closed, and holds the restart lock for
        the whole startup, so a ``shutdown`` that begins meanwhile waits for it (it sets
        ``_closed`` first) and no process outlives the closed backend: the flag is
        checked before every candidate spawn and again once a candidate is initialized,
        and a close error is raised outside the per-candidate catch so it is never
        recorded as a failed attempt that lets the next candidate start.
        """
        async with self._restart_lock:
            startup_errors: list[str] = []
            for command in self._candidate_commands():
                self._require_open()
                self._client = self._make_client()
                try:
                    await self._client.start(command)
                    await self._initialize_session()
                except (Exception, asyncio.CancelledError) as exc:
                    try:
                        await self._client.shutdown()
                    except Exception:
                        _LOGGER.warning("Could not clean up failed Pyright startup attempt.", exc_info=True)
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                    startup_errors.append(f"{' '.join(command)} -> {exc}")
                else:
                    if self._closed:
                        try:
                            await self._client.shutdown()
                        except Exception:
                            # The close error below wins; ``shutdown`` retries stopping this client.
                            _LOGGER.warning("Could not stop Pyright started during shutdown.", exc_info=True)
                        self._require_open()
                    self._startup_command = command
                    return

            self._require_open()
            joined_errors = " | ".join(startup_errors)
            raise PyrightError(f"Unable to start pyright language server. Attempts: {joined_errors}")

    def _require_open(self) -> None:
        """Raise ``PyrightError`` once :meth:`shutdown` has closed this backend."""
        if self._closed:
            raise PyrightError("Pyright backend is shut down.")

    async def shutdown(self) -> None:
        """Close the backend for good and stop its language server.

        ``_closed`` is set before waiting for the restart lock, so no new restart
        starts and one already running either finishes first (and is stopped here)
        or notices the flag and stops its own process. No request can respawn the
        server afterwards.
        """
        self._closed = True
        async with self._restart_lock:
            await self._client.shutdown()

    # ── File tracking ─────────────────────────────────────────────────

    def _clear_documents(self) -> None:
        self._open_files.clear()
        self._file_versions.clear()
        self._file_contents.clear()
        self._file_stamps.clear()

    def _read_document(self, absolute_path: str) -> tuple[str, tuple[int, int]]:
        """Return the file's text and the stat stamp taken before it was read."""
        try:
            stamp = stamp_of(absolute_path)
            return Path(absolute_path).read_text(encoding="utf-8"), stamp
        except FileNotFoundError as exc:
            raise ToolInputError(f"file_path does not exist: {absolute_path}") from exc
        except (UnicodeDecodeError, OSError) as exc:
            raise PyrightError(f"Cannot read file {absolute_path}: {exc}") from exc

    async def ensure_file_open(self, file_path: str) -> None:
        """Open a document in the language server session if needed."""
        absolute_path = normalize_path(file_path)
        await self._ensure_healthy()
        async with self._document_lock:
            if absolute_path not in self._file_contents:
                text, stamp = self._read_document(absolute_path)
                await self._sync_document(absolute_path, text, stamp)

    async def _refresh_document(self, absolute_path: str, transport: LSPClient) -> None:
        """Synchronize current disk contents with Pyright before analysis."""
        async with self._document_lock:
            self._require_current_session(transport)
            text, stamp = self._read_document(absolute_path)
            if self._file_contents.get(absolute_path) != text:
                await self._sync_document(absolute_path, text, stamp)
            else:
                self._file_stamps[absolute_path] = stamp

    def _require_current_session(self, transport: LSPClient) -> None:
        if transport is not self._client or self._session_invalid:
            raise PyrightError("Pyright session changed while preparing the document.")

    async def _sync_peer_documents(self, transport: LSPClient, *, skip: str | None = None) -> None:
        """Resynchronize every other open document whose file changed on disk.

        Pyright analyzes a file against the open-document text of everything it imports,
        so a dependency edited outside this server must reach the language server before
        its importer is analyzed. Unchanged files cost one ``stat``; a deleted or
        unreadable one is closed instead of failing the analysis of an unrelated file.
        """
        async with self._document_lock:
            self._require_current_session(transport)
            for path in sorted(self._open_files):
                if path != skip:
                    await self._resync_peer(path)

    async def _resync_peer(self, absolute_path: str) -> None:
        """Bring one open document up to date, or close it when its file is gone. Lock held."""
        try:
            stamp = stamp_of(absolute_path)
        except OSError:
            await self._close_document(absolute_path)
            return
        if absolute_path in self._file_contents and self._file_stamps.get(absolute_path) == stamp:
            return
        try:
            text, stamp = self._read_document(absolute_path)
        except (ToolInputError, PyrightError):
            _LOGGER.warning("Closing unreadable open document %s", absolute_path, exc_info=True)
            await self._close_document(absolute_path)
            return
        if self._file_contents.get(absolute_path) == text:
            self._file_stamps[absolute_path] = stamp
        else:
            await self._sync_document(absolute_path, text, stamp)

    async def _close_document(self, absolute_path: str) -> None:
        """Forget a document and tell the server to close it. Lock held.

        Versions stay monotonic across a close/open cycle, so a reopened document never
        reuses an old version number.
        """
        self._open_files.discard(absolute_path)
        self._file_contents.pop(absolute_path, None)
        self._file_stamps.pop(absolute_path, None)
        try:
            await self._client.send_notification(
                "textDocument/didClose", {"textDocument": {"uri": path_to_uri(absolute_path)}}
            )
        except (Exception, asyncio.CancelledError):
            # The server may still hold the document; only a fresh session is certain.
            self._session_invalid = True
            raise

    async def _sync_document(self, absolute_path: str, text: str, stamp: tuple[int, int]) -> None:
        """Send document contents while holding the document lock."""
        if self._session_invalid:
            raise PyrightError("Pyright session is unavailable while synchronizing the document.")
        file_uri = path_to_uri(absolute_path)
        previous_version = self._file_versions.get(absolute_path)
        version = 1 if previous_version is None else previous_version + 1
        self._file_versions[absolute_path] = version
        self._file_contents.pop(absolute_path, None)
        self._file_stamps.pop(absolute_path, None)

        document: dict[str, JSONValue] = {"uri": file_uri, "version": version}
        if absolute_path in self._open_files:
            await self._client.send_notification(
                "textDocument/didChange",
                {"textDocument": document, "contentChanges": [{"text": text}]},
            )
        else:
            document.update({"languageId": "python", "text": text})
            try:
                await self._client.send_notification("textDocument/didOpen", {"textDocument": document})
            except (Exception, asyncio.CancelledError):
                # The server may have received the open before the send was interrupted.
                self._session_invalid = True
                raise
            self._open_files.add(absolute_path)
        self._file_contents[absolute_path] = text
        self._file_stamps[absolute_path] = stamp

    async def _on_healthy_transport(self, operation: Callable[[LSPClient], Awaitable[None]]) -> None:
        """Run ``operation`` on the live transport, once more on a replacement after a crash."""
        client = await self._ensure_healthy()
        try:
            await operation(client)
        except (BrokenPipeError, ConnectionResetError):
            replacement = await self._ensure_healthy(disconnected=client)
            await operation(replacement)
        except PyrightError:
            if client is self._client and self.is_running:
                raise
            replacement = await self._ensure_healthy()
            await operation(replacement)

    async def notify_file_changed(self, file_path: str) -> None:
        """Synchronize an edited file and invalidate its previous diagnostics."""
        absolute_path = normalize_path(file_path)

        async def synchronize(transport: LSPClient) -> None:
            await asyncio.wait_for(
                self._refresh_document(absolute_path, transport),
                timeout=self._request_timeout_seconds,
            )

        try:
            await self._on_healthy_transport(synchronize)
        except (ToolInputError, BrokenPipeError, ConnectionResetError, TimeoutError) as exc:
            raise PyrightError("Could not synchronize edited file with Pyright.") from exc

    # ── Diagnostics ───────────────────────────────────────────────────

    async def get_diagnostics(self, file_path: str) -> list[Diagnostic]:
        """Return the analyzed diagnostics of one file.

        The file is analyzed after every open document that changed on disk has been
        resynchronized, so an edited dependency is seen by its importer.
        """
        return await self._pull_diagnostics(normalize_path(file_path), sync_peers=True)

    async def get_diagnostics_many(
        self,
        file_paths: Sequence[str],
        *,
        concurrency: int = 1,
        stop_on_error: bool = False,
        close_opened: bool = False,
    ) -> list[list[Diagnostic] | Exception]:
        """Return per-file diagnostics for a batch after ONE resync of the open documents.

        A per-file failure is returned in that file's slot (``Exception`` only:
        cancellation propagates). ``stop_on_error`` runs sequentially and ends the
        result at the first failure; it cannot be combined with ``concurrency > 1``.
        A failure of the shared resync itself (timeout, dead session) raises.

        ``close_opened`` closes, once the batch ends (also on failure or cancellation),
        the documents this call opened, so a whole-workspace scan does not grow the
        open set; documents that were already open stay open. A document another
        request opens meanwhile may be closed too; its next request reopens it.

        Limitation: a document is detected as changed by its ``(mtime_ns, size)``
        stamp, so an edit that keeps both the size and the modification time is not
        noticed until the file changes again or the session restarts.
        """
        if not close_opened:
            return await self._pull_many(file_paths, concurrency=concurrency, stop_on_error=stop_on_error)
        already_open = set(self._open_files)
        scanned: set[str] = set()
        for path in file_paths:
            with contextlib.suppress(Exception):  # a bad path is reported by its own pull
                scanned.add(normalize_path(path))
        try:
            return await self._pull_many(file_paths, concurrency=concurrency, stop_on_error=stop_on_error)
        finally:
            await self._close_documents(scanned - already_open)

    async def _close_documents(self, paths: set[str]) -> None:
        """Close the still-open documents among ``paths``; a failure invalidates the session, never the caller."""
        try:
            async with self._document_lock:
                for path in sorted(paths):
                    if path in self._open_files:
                        await self._close_document(path)
        except Exception:
            _LOGGER.warning("Could not close scanned documents; the next request restarts the session.", exc_info=True)

    async def _pull_many(
        self,
        file_paths: Sequence[str],
        *,
        concurrency: int,
        stop_on_error: bool,
    ) -> list[list[Diagnostic] | Exception]:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        if stop_on_error and concurrency != 1:
            raise ValueError("stop_on_error requires concurrency=1")
        if not file_paths:
            return []

        async def resync(transport: LSPClient) -> None:
            await asyncio.wait_for(
                self._sync_peer_documents(transport),
                timeout=self._request_timeout_seconds,
            )

        try:
            await self._on_healthy_transport(resync)
        except TimeoutError as exc:
            raise PyrightError("Could not resynchronize open documents with Pyright in time.") from exc

        async def one(path: str) -> list[Diagnostic] | Exception:
            try:
                return await self._pull_diagnostics(normalize_path(path), sync_peers=False)
            except Exception as exc:
                return exc

        if concurrency == 1:
            results: list[list[Diagnostic] | Exception] = []
            for path in file_paths:
                result = await one(path)
                results.append(result)
                if stop_on_error and isinstance(result, Exception):
                    break
            return results
        gate = asyncio.Semaphore(concurrency)

        async def bounded(path: str) -> list[Diagnostic] | Exception:
            async with gate:
                return await one(path)

        pulls = [asyncio.ensure_future(bounded(path)) for path in file_paths]
        try:
            return list(await asyncio.gather(*pulls))
        except BaseException:
            # A cancelled pull (or our own cancellation) must not leave siblings running.
            for pull in pulls:
                pull.cancel()
            await asyncio.gather(*pulls, return_exceptions=True)
            raise

    async def _pull_diagnostics(self, normalized: str, *, sync_peers: bool) -> list[Diagnostic]:
        """Pull one file's diagnostics, optionally resynchronizing the other open documents first."""

        async def prepare(transport: LSPClient) -> None:
            if sync_peers:
                await self._sync_peer_documents(transport, skip=normalized)
            await self._refresh_document(normalized, transport)

        response = await self._request(
            "textDocument/diagnostic",
            {"textDocument": {"uri": path_to_uri(normalized)}},
            prepare=prepare,
        )
        if is_unhandled_method_error(response):
            raise LspFeatureUnsupportedError("Pyright does not implement textDocument/diagnostic.")
        if "error" in response:
            raise PyrightError(f"textDocument/diagnostic failed: {response['error']}")
        report = response.get("result")
        if not isinstance(report, dict) or report.get("kind") != "full":
            raise PyrightError("Expected a full textDocument/diagnostic report.")
        items = report.get("items")
        if not isinstance(items, list):
            raise PyrightError("Expected an items array in the textDocument/diagnostic report.")
        try:
            return _sorted_diagnostics(convert_diagnostics(normalized, items))
        except ValueError as exc:
            raise PyrightError("Invalid diagnostic in the textDocument/diagnostic report.") from exc

    # ── Analysis features ─────────────────────────────────────────────

    async def _document_request(
        self,
        method: str,
        params: dict[str, JSONValue],
        absolute_path: str,
        *,
        validate: Callable[[], None] | None = None,
    ) -> JSONDict:
        """Issue a file-bound LSP request with the document synchronized on the transport that sends it.

        The synchronization runs inside the request's ``prepare`` step, so a
        replay on a replacement session (after a crash) reopens the document
        there first, and an edited file is re-synchronized before analysis.
        ``validate`` runs after synchronization, on the synchronized contents.
        """

        async def prepare(transport: LSPClient) -> None:
            await self._refresh_document(absolute_path, transport)
            if validate is not None:
                validate()

        return await self._request(method, params, prepare=prepare)

    async def _position_request(
        self,
        lsp_method: str,
        absolute_path: str,
        line: int,
        char: int,
        extra_params: dict[str, JSONValue] | None = None,
    ) -> JSONDict:
        """Open the file and issue an LSP ``textDocument``/``position`` request.

        Builds the canonical ``{"textDocument": ..., "position": ...}`` envelope
        shared by every position-based feature, merges any ``extra_params``
        without letting them clobber the envelope keys, and returns the raw
        response dict. Callers retain their own error-check and result dispatch.

        Out-of-range ``line``/``char`` coordinates raise :class:`ToolInputError`
        (surfaced as ``[INVALID_INPUT]`` naming the parameter) before the LSP
        round-trip, so a bad coordinate is distinguishable from a genuine
        zero-result (Pyright silently returns ``null`` for both) and from a
        backend outage.
        """
        params: dict[str, JSONValue] = {
            "textDocument": {"uri": path_to_uri(absolute_path)},
            "position": {"line": line, "character": char},
        }
        if extra_params:
            reserved = {"textDocument", "position"} & extra_params.keys()
            if reserved:
                names = ", ".join(sorted(reserved))
                raise ValueError(f"extra_params may not override reserved LSP envelope keys: {names}")
            params.update(extra_params)

        return await self._document_request(
            lsp_method,
            params,
            absolute_path,
            validate=lambda: self._validate_position(absolute_path, line, char),
        )

    def _validate_position(self, absolute_path: str, line: int, char: int) -> None:
        """Bounds-check a 0-based LSP position against the file's contents.

        A valid line is ``0 <= line < line_count``; a valid character is
        ``0 <= char <= utf16_len(line_text)`` — LSP ``character`` counts UTF-16
        code units, so an astral code point widens the bound by two — and the
        column may equal that length to address an end-of-line position. This is the read-path analogue of
        :meth:`RopeBackend._position_to_offset`'s validation; it is marginally
        stricter — rope additionally accepts the virtual position just past a
        trailing newline (``line == line_count``, ``char == 0``), which this
        read-only check rejects. Raises :class:`ToolInputError` naming ``line``
        or ``character`` on any out-of-range coordinate so callers see an
        ``[INVALID_INPUT]`` error instead of an ambiguous empty result or a
        redacted backend failure. A missing content cache for an open file is
        server-internal state, not caller input, and stays :class:`PyrightError`.
        """
        if line < 0:
            raise ToolInputError(f"line must be non-negative (0-based); got {line}")
        if char < 0:
            raise ToolInputError(f"character must be non-negative (0-based); got {char}")

        text = self._file_contents.get(absolute_path)
        if text is None:
            raise PyrightError(f"File content cache is missing for open file: {absolute_path}")

        lines = text.splitlines() or [""]
        if line >= len(lines):
            raise ToolInputError(
                f"line {line} is out of range: the file has {len(lines)} line(s) "
                f"(valid 0-based lines are 0..{len(lines) - 1})"
            )

        line_text = lines[line]
        line_length = _code_point_to_utf16_offset(line_text, len(line_text))
        if char > line_length:
            raise ToolInputError(
                f"character {char} is out of range: line {line} has {line_length} "
                f"UTF-16 code unit(s) (valid 0-based characters are 0..{line_length})"
            )

    async def get_hover(self, file_path: str, line: int, char: int) -> TypeInfo | None:
        """Get hover type information at a source position."""
        absolute_path = normalize_path(file_path)
        response = await self._position_request("textDocument/hover", absolute_path, line, char)
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
        response = await self._document_request(
            "textDocument/documentSymbol",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
            },
            absolute_path,
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
        response = await self._position_request("textDocument/completion", absolute_path, line, char)
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
        response = await self._position_request(
            "textDocument/references",
            absolute_path,
            line,
            char,
            extra_params={"context": {"includeDeclaration": include_declaration}},
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
        response = await self._position_request("textDocument/definition", absolute_path, line, char)
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
        self._require_capability("implementationProvider", "textDocument/implementation")
        absolute_path = normalize_path(file_path)
        response = await self._position_request("textDocument/implementation", absolute_path, line, char)
        if "error" in response:
            if is_unhandled_method_error(response):
                raise LspFeatureUnsupportedError(
                    f"textDocument/implementation unhandled by Pyright: {response['error']}"
                )
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
        response = await self._position_request("textDocument/signatureHelp", absolute_path, line, char)
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
        response = await self._position_request(
            "textDocument/prepareCallHierarchy", absolute_path, line, char
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
        self._require_capability("typeHierarchyProvider", "textDocument/prepareTypeHierarchy")
        absolute_path = normalize_path(file_path)
        response = await self._position_request(
            "textDocument/prepareTypeHierarchy", absolute_path, line, char
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                raise LspFeatureUnsupportedError(
                    f"textDocument/prepareTypeHierarchy unhandled by Pyright: {response['error']}"
                )
            raise PyrightError(f"prepareTypeHierarchy failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []
        return [type_hierarchy_item_to_model(item) for item in result if isinstance(item, dict)]

    async def get_supertypes(self, item: TypeHierarchyItem) -> list[TypeHierarchyItem]:
        """Return direct supertypes for a type hierarchy item."""
        self._require_capability("typeHierarchyProvider", "typeHierarchy/supertypes")
        response = await self._request(
            "typeHierarchy/supertypes",
            {"item": type_hierarchy_item_to_lsp(item)},
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                raise LspFeatureUnsupportedError(
                    f"typeHierarchy/supertypes unhandled by Pyright: {response['error']}"
                )
            raise PyrightError(f"typeHierarchy/supertypes failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []
        return [type_hierarchy_item_to_model(entry) for entry in result if isinstance(entry, dict)]

    async def get_subtypes(self, item: TypeHierarchyItem) -> list[TypeHierarchyItem]:
        """Return direct subtypes for a type hierarchy item."""
        self._require_capability("typeHierarchyProvider", "typeHierarchy/subtypes")
        response = await self._request(
            "typeHierarchy/subtypes",
            {"item": type_hierarchy_item_to_lsp(item)},
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                raise LspFeatureUnsupportedError(
                    f"typeHierarchy/subtypes unhandled by Pyright: {response['error']}"
                )
            raise PyrightError(f"typeHierarchy/subtypes failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, list):
            return []
        return [type_hierarchy_item_to_model(entry) for entry in result if isinstance(entry, dict)]

    # ── Selection / folding / highlights ──────────────────────────────

    async def get_selection_range(self, file_path: str, positions: list[Position]) -> list[SelectionRangeResult]:
        """Return nested selection ranges for one or more positions."""
        self._require_capability("selectionRangeProvider", "textDocument/selectionRange")
        absolute_path = normalize_path(file_path)
        response = await self._document_request(
            "textDocument/selectionRange",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "positions": [
                    {"line": position.line, "character": position.character}
                    for position in positions
                ],
            },
            absolute_path,
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                raise LspFeatureUnsupportedError(
                    f"textDocument/selectionRange unhandled by Pyright: {response['error']}"
                )
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
        response = await self._document_request("textDocument/codeAction", request_params, absolute_path)
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
        response = await self._position_request("textDocument/declaration", absolute_path, line, char)
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
        self._require_capability("typeDefinitionProvider", "textDocument/typeDefinition")
        absolute_path = normalize_path(file_path)
        response = await self._position_request("textDocument/typeDefinition", absolute_path, line, char)
        if "error" in response:
            if is_unhandled_method_error(response):
                raise LspFeatureUnsupportedError(
                    f"textDocument/typeDefinition unhandled by Pyright: {response['error']}"
                )
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
        response = await self._position_request(
            "textDocument/documentHighlight", absolute_path, line, char
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
        response = await self._position_request("textDocument/prepareRename", absolute_path, line, char)
        if "error" in response:
            if is_unhandled_method_error(response):
                return None
            raise PyrightError(f"prepareRename request failed: {response['error']}")

        result = response.get("result")
        if not isinstance(result, dict):
            return None

        # LSP PrepareRenameResult has three shapes: `{range, placeholder}`, a bare
        # `Range` (`{start, end}`), and `{defaultBehavior: true}`.
        range_value: JSONValue
        if "range" in result:
            range_value = result.get("range")
            placeholder = as_str(result.get("placeholder"), "")
        elif "start" in result and "end" in result:
            range_value = result
            placeholder = ""
        elif result.get("defaultBehavior") is True:
            # The server accepts the position but leaves range computation to the
            # client: derive the identifier span under the cursor.
            try:
                source_lines = Path(absolute_path).read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                return None
            if not 0 <= line < len(source_lines):
                return None
            line_text = source_lines[line]

            def is_identifier_char(index: int) -> bool:
                return 0 <= index < len(line_text) and (line_text[index].isalnum() or line_text[index] == "_")

            # LSP ``character`` counts UTF-16 code units; scan the line by code point.
            cursor = _utf16_to_code_point_index(line_text, char)
            anchor = cursor if is_identifier_char(cursor) else cursor - 1
            if not is_identifier_char(anchor):
                return None
            start_char = anchor
            while is_identifier_char(start_char - 1):
                start_char -= 1
            end_char = anchor + 1
            while is_identifier_char(end_char):
                end_char += 1
            range_value = {
                "start": {"line": line, "character": _code_point_to_utf16_offset(line_text, start_char)},
                "end": {"line": line, "character": _code_point_to_utf16_offset(line_text, end_char)},
            }
            placeholder = line_text[start_char:end_char]
        else:
            return None

        if not isinstance(range_value, dict):
            return None

        if not placeholder:
            try:
                source_lines = Path(absolute_path).read_text(encoding="utf-8").splitlines()
                mr = model_range(range_value)
                start_line = mr.start.line
                if 0 <= start_line < len(source_lines):
                    line_text = source_lines[start_line]
                    start_char = _utf16_to_code_point_index(line_text, mr.start.character)
                    end_char = (
                        _utf16_to_code_point_index(line_text, mr.end.character)
                        if mr.end.line == start_line
                        else len(line_text)
                    )
                    placeholder = line_text[start_char:end_char].strip() or Path(absolute_path).stem
                else:
                    placeholder = Path(absolute_path).stem
            except (OSError, UnicodeError):
                # Placeholder extraction is optional; the module stem remains a
                # deterministic fallback when the source cannot be decoded/read.
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
        self._require_capability("inlayHintProvider", "textDocument/inlayHint")
        absolute_path = normalize_path(file_path)
        response = await self._document_request(
            "textDocument/inlayHint",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
                "range": {
                    "start": {"line": start_line, "character": start_character},
                    "end": {"line": end_line, "character": end_character},
                },
            },
            absolute_path,
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                raise LspFeatureUnsupportedError(
                    f"textDocument/inlayHint unhandled by Pyright: {response['error']}"
                )
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
        self._require_capability("semanticTokensProvider", "textDocument/semanticTokens/full")
        absolute_path = normalize_path(file_path)
        response = await self._document_request(
            "textDocument/semanticTokens/full",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
            },
            absolute_path,
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                raise LspFeatureUnsupportedError(
                    f"textDocument/semanticTokens/full unhandled by Pyright: {response['error']}"
                )
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
        self._require_capability("foldingRangeProvider", "textDocument/foldingRange")
        absolute_path = normalize_path(file_path)
        response = await self._document_request(
            "textDocument/foldingRange",
            {
                "textDocument": {"uri": path_to_uri(absolute_path)},
            },
            absolute_path,
        )
        if "error" in response:
            if is_unhandled_method_error(response):
                raise LspFeatureUnsupportedError(
                    f"textDocument/foldingRange unhandled by Pyright: {response['error']}"
                )
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

    async def restart_server(self) -> str:
        """Restart Pyright analysis, discarding cached type information."""
        async with self._restart_lock:
            await self._restart()
        return "Pyright server restarted successfully"
