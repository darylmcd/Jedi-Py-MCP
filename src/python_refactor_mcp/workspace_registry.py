"""Dynamic multi-workspace backend registry with lazy init and LRU eviction."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from python_refactor_mcp.backends.jedi_backend import JediBackend
from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient
from python_refactor_mcp.backends.rope_backend import RopeBackend
from python_refactor_mcp.config import ServerConfig, discover_config
from python_refactor_mcp.errors import AmbiguousWorkspaceError, WorkspaceResolutionError

_LOGGER = logging.getLogger(__name__)

# Project markers used to discover workspace roots by walking parent directories.
_PROJECT_MARKERS = (".git", "pyproject.toml", "setup.py", "setup.cfg")


async def _run_to_completion(coro: Coroutine[Any, Any, None]) -> None:
    """Run *coro* to completion even if the awaiting task is cancelled (once or repeatedly).

    The cancellation is re-raised after the work finishes. The task is held in a local
    so a second cancellation cannot drop the only reference to it. A failure of the
    task is retrieved and logged rather than left unretrieved: the cancellation
    outranks it, so it cannot propagate.
    """
    task = asyncio.ensure_future(coro)
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.wait({task})
            except asyncio.CancelledError:
                continue
        if not task.cancelled():
            failure = task.exception()
            if failure is not None:
                _LOGGER.warning("Cleanup task failed while its caller was cancelled", exc_info=failure)
        raise


async def _shutdown_all(backends_list: list[WorkspaceBackends]) -> None:
    """Shut every backend in *backends_list* down, one after another."""
    for backends in backends_list:
        _LOGGER.info("Shutting down workspace: %s", backends.config.workspace_root)
        await backends.shutdown()


@dataclass(eq=False)
class WorkspaceBackends:
    """Per-workspace backend triad with lifecycle management.

    Field names (pyright, jedi, rope, config) intentionally mirror the old
    AppContext so that tool functions work unchanged after the switch. Compared and
    hashed by identity: the registry keeps sets of live instances.
    """

    config: ServerConfig
    pyright: PyrightLSPClient
    jedi: JediBackend
    rope: RopeBackend
    last_accessed: float = field(default_factory=time.monotonic)
    # True once a path-bearing request chose this workspace. The startup pre-warm
    # leaves it False, so a path-less call cannot silently adopt it.
    selected: bool = False
    _initialized: bool = field(default=False, repr=False)
    # In-flight requests holding these backends. Changed only through
    # :meth:`WorkspaceRegistry.release` and the registry's lookups, which acquire.
    leases: int = field(default=0, repr=False)
    # True once the registry unregistered these backends: they are shut down as soon
    # as the last lease is released (immediately when none is held).
    retired: bool = field(default=False, repr=False)

    def acquire(self) -> None:
        """Claim these backends for one request. Paired with :meth:`WorkspaceRegistry.release`."""
        self.leases += 1

    def drop_lease(self) -> None:
        """Give one lease back; a release with no matching acquire is a defect and raises."""
        if self.leases <= 0:
            raise RuntimeError("Workspace backends released more often than acquired")
        self.leases -= 1

    async def initialize(self) -> None:
        """Start all three backends for this workspace.

        A failure (or cancellation) after any backend started releases everything
        already started before re-raising, so no subprocess outlives a failed start.
        """
        if self._initialized:
            return
        try:
            await self.pyright.start()
            self.jedi.initialize()
            self.rope.initialize()
        except BaseException:
            await _run_to_completion(self._release_resources())
            raise
        self._initialized = True

    async def shutdown(self) -> None:
        """Stop all backends, releasing subprocess and file handles."""
        if not self._initialized:
            return
        self._initialized = False
        await _run_to_completion(self._release_resources())

    async def _release_resources(self) -> None:
        """Stop Pyright and close Rope. Safe on partially started backends; swallows Exception only."""
        try:
            await self.pyright.shutdown()
        except Exception:
            _LOGGER.warning("Pyright shutdown failed for %s", self.config.workspace_root, exc_info=True)
        finally:
            try:
                self.rope.close()
            except Exception:
                _LOGGER.warning("Rope close failed for %s", self.config.workspace_root, exc_info=True)

    def touch(self) -> None:
        """Update last-accessed timestamp for LRU tracking."""
        self.last_accessed = time.monotonic()

    @property
    def is_initialized(self) -> bool:
        """Whether this workspace's backend triad has been started."""
        return self._initialized


class WorkspaceRegistry:
    """Manages per-workspace backend instances with lazy init and LRU eviction.

    Thread safety: all mutations are guarded by an asyncio.Lock.

    Leases: :meth:`get_backends` and :meth:`implicit_workspace` hand out backends with one
    lease acquired; the caller must :meth:`release` it. A workspace that eviction or
    ``set_roots`` removes while leased leaves the registry at once (so capacity accounting
    and new requests are unaffected) but is shut down only when its last lease is released,
    so live backends may briefly exceed ``max_workspaces`` by the number of in-flight
    requests on evicted workspaces. :meth:`shutdown_all` stops everything, leased or not.
    """

    def __init__(self, max_workspaces: int = 3) -> None:
        if max_workspaces < 1:
            raise ValueError("max_workspaces must be >= 1")
        self._max_workspaces = max_workspaces
        self._workspaces: dict[Path, WorkspaceBackends] = {}
        self._known_roots: list[Path] = []
        # Invariant: a subset of _known_roots. Roots found by marker discovery rather
        # than registered through set_roots; they are evicted ahead of explicit roots.
        self._auto_roots: set[Path] = set()
        # Unregistered backends still held by a request: shut down on their last release,
        # or by shutdown_all. Leases are only taken while registered, so none is added here.
        self._retired_live: set[WorkspaceBackends] = set()
        # Deferred shutdowns started by release(); strong references until done.
        self._retiring: set[asyncio.Task[None]] = set()
        self._closed = False
        self._lock = asyncio.Lock()

    # ── Root management ──────────────────────────────────────────────────

    async def set_roots(self, roots: list[Path]) -> None:
        """Update the set of known workspace roots.

        Retires backends for any roots that were removed. The removed workspaces
        leave the registry in the same step that replaces the roots, and are marked
        retired, before any shutdown is awaited. Idle ones are shut down before this
        returns, even if the caller is cancelled; one a request still holds is shut down
        when that request releases it. Does NOT eagerly initialize new roots (lazy on
        first tool call).
        """
        resolved = [r.resolve() for r in roots]
        async with self._lock:
            self._require_open()
            old_set = set(self._known_roots)
            new_set = set(resolved)
            removed = old_set - new_set

            self._known_roots = resolved
            # Every root passed here is explicit, including one previously auto-discovered.
            self._auto_roots.clear()

            popped = [self._workspaces.pop(root) for root in removed if root in self._workspaces]
            idle = self._retire(popped)
            await _run_to_completion(_shutdown_all(idle))

    def get_known_roots(self) -> list[Path]:
        """Return a copy of the current known roots list."""
        return list(self._known_roots)

    # ── Backend access (hot path) ────────────────────────────────────────

    async def get_backends(self, file_path: str) -> WorkspaceBackends:
        """Resolve the workspace enclosing *file_path*, lazily initialize it, select it, and return backends.

        This is the hot path — the boundary calls it with the first workspace-selecting
        path of every request that has one (``file_path``, ``root_path``, the other
        ``PATH_PARAMS``, list and nested paths). The workspace is marked selected, so
        later path-less calls may resolve to it (see :meth:`implicit_workspace`).

        The backends come with one lease acquired, in the same step as the lookup: the
        caller must pass them to :meth:`release` when its request ends.
        """
        root = self.resolve_workspace_root(Path(file_path).resolve())
        return await self._get_or_create(root, claim=True)

    async def prewarm(self, root: Path) -> WorkspaceBackends:
        """Start the workspace enclosing *root* without selecting it or leasing it.

        Used for the startup pre-warm: the backends are ready, but a path-less call
        still has to name its workspace (see :meth:`implicit_workspace`).
        """
        return await self._get_or_create(self.resolve_workspace_root(root.resolve()), claim=False)

    def release(self, backends: WorkspaceBackends) -> None:
        """Give back the lease taken by :meth:`get_backends` or :meth:`implicit_workspace`.

        Synchronous and lock-free, so it is safe in a ``finally`` during cancellation. The
        last release of an unregistered workspace starts its shutdown (tracked, and awaited
        by :meth:`shutdown_all`); after shutdown_all it starts nothing.
        """
        backends.drop_lease()
        if backends.leases == 0 and backends.retired:
            self._retired_live.discard(backends)
            self._schedule_shutdown(backends)

    def _require_open(self) -> None:
        """Raise once :meth:`shutdown_all` has run: a closed registry creates no workspace."""
        if self._closed:
            raise WorkspaceResolutionError("The workspace registry is shut down; the server is stopping.")

    async def _get_or_create(self, root: Path, *, claim: bool) -> WorkspaceBackends:
        """Return the live backends of *root*, evicting and initializing as needed.

        With *claim* the caller's lease and selection are taken inside the lock with no
        await after the lookup, so the workspace cannot be evicted in between.
        """
        async with self._lock:
            self._require_open()
            backends = self._workspaces.get(root)
            if backends is None:
                await self._evict_lru()
                backends = await self._initialize_workspace(root)
            else:
                backends.touch()
            if claim:
                backends.acquire()
                backends.selected = True
            return backends

    def implicit_workspace(self) -> WorkspaceBackends:
        """Return the workspace a call that names no path means, or raise when that is not unambiguous.

        Only a sole live workspace that a path-bearing request already selected qualifies;
        it is touched so the LRU sees the use, and comes with one lease the caller must
        :meth:`release`. Several live workspaces, a pre-warmed root no request has
        selected, and an empty registry raise :class:`AmbiguousWorkspaceError` naming the
        live roots and the ``root_path`` parameter.
        """
        live = self.active_backends()
        if len(live) == 1 and live[0].selected:
            live[0].touch()
            live[0].acquire()
            return live[0]

        if not live:
            detail = "no workspace is live"
        else:
            roots = ", ".join(
                f"{backends.config.workspace_root}{'' if backends.selected else ' (pre-warmed, not selected)'}"
                for backends in live
            )
            detail = f"{len(live)} workspace{'s are' if len(live) > 1 else ' is'} live: {roots}"
        raise AmbiguousWorkspaceError(
            f"This call names no file or root_path and {detail}. "
            "Pass an absolute root_path naming the target workspace."
        )

    def active_backends(self) -> list[WorkspaceBackends]:
        """Return the currently-initialized workspace backends.

        Read-only snapshot for status reporting; ordered by most-recently
        accessed first. Does not touch LRU state or issue backend requests.
        """
        return sorted(self._workspaces.values(), key=lambda b: b.last_accessed, reverse=True)

    # ── Workspace resolution ─────────────────────────────────────────────

    def resolve_workspace_root(self, file_path: Path) -> Path:
        """Return the deepest known root or project marker enclosing a path.

        Pure: it never registers a root. A root found by marker is recorded by
        :meth:`_get_or_create` once its backends have started.
        """
        resolved = file_path.resolve()
        if resolved in self._known_roots:
            return resolved

        directory = resolved if resolved.is_dir() else resolved.parent
        for parent in (directory, *directory.parents):
            if parent in self._known_roots:
                return parent
            for marker in _PROJECT_MARKERS:
                if (parent / marker).exists():
                    return parent

        raise WorkspaceResolutionError(
            f"Cannot determine workspace root for: {file_path}. "
            f"No project markers ({', '.join(_PROJECT_MARKERS)}) found in enclosing directories, "
            f"and the path is not under any known root."
        )

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def _initialize_workspace(self, root: Path) -> WorkspaceBackends:
        """Create and start backends for a workspace root. Caller must hold _lock.

        A root that is not yet known is registered as auto-discovered only after
        ``initialize()`` succeeds, so a failed start leaves no root without a backend.
        """
        _LOGGER.info("Initializing workspace backends for: %s", root)
        config = discover_config(root)
        backends = WorkspaceBackends(
            config=config,
            pyright=PyrightLSPClient(config),
            jedi=JediBackend(config),
            rope=RopeBackend(config),
        )
        await backends.initialize()
        self._workspaces[root] = backends
        if root not in self._known_roots:
            self._known_roots.append(root)
            self._auto_roots.add(root)
            _LOGGER.info("Auto-discovered workspace root: %s", root)
        return backends

    def _eviction_key(self, root: Path, backends: WorkspaceBackends) -> tuple[bool, float]:
        """Sort key for eviction; the smallest key is evicted first.

        Auto-discovered roots go before explicit ones; least recently used first within each class.
        """
        return (root not in self._auto_roots, backends.last_accessed)

    def _retire(self, popped: list[WorkspaceBackends]) -> list[WorkspaceBackends]:
        """Mark just-unregistered *popped* retired and return those no request holds.

        Synchronous on purpose: every backend is marked before the caller's first await,
        so a cancellation mid-shutdown cannot leave a leased one unmarked (it would never
        be shut down). A leased one is remembered for :meth:`shutdown_all` and shut down by
        its last :meth:`release`. Caller holds _lock and has already removed *popped*
        from ``_workspaces``, so no further lease can be taken on them.
        """
        idle: list[WorkspaceBackends] = []
        for backends in popped:
            backends.retired = True
            if backends.leases > 0:
                self._retired_live.add(backends)
            else:
                idle.append(backends)
        return idle

    def _schedule_shutdown(self, backends: WorkspaceBackends) -> None:
        """Start the tracked shutdown of a retired backend whose last lease was released.

        Starts nothing once the registry is closed (shutdown_all already stopped every
        backend and gathers the tasks it started) or when the backend is already stopped.
        """
        if self._closed or not backends.is_initialized:
            return
        task = asyncio.ensure_future(backends.shutdown())
        self._retiring.add(task)
        task.add_done_callback(self._retiring_done)

    def _retiring_done(self, task: asyncio.Task[None]) -> None:
        """Forget a finished deferred shutdown and log its failure instead of leaving it unretrieved."""
        self._retiring.discard(task)
        if not task.cancelled() and task.exception() is not None:
            _LOGGER.warning("Deferred workspace shutdown failed", exc_info=task.exception())

    async def _evict_lru(self) -> None:
        """Evict the least-recently-used workspace if at capacity. Caller must hold _lock.

        Never waits for the victim's requests: it is unregistered now and, when a request
        still holds it, shut down on that request's release.
        """
        if len(self._workspaces) < self._max_workspaces:
            return

        candidates = sorted(self._workspaces.items(), key=lambda kv: self._eviction_key(*kv))
        evict_root, evict_backends = candidates[0]
        _LOGGER.info("Evicting LRU workspace: %s (last_accessed=%.1f)", evict_root, evict_backends.last_accessed)
        del self._workspaces[evict_root]
        for idle in self._retire([evict_backends]):
            await idle.shutdown()

    async def _stop_everything(self, backends_list: list[WorkspaceBackends]) -> None:
        """Shut *backends_list* down, then wait for every deferred shutdown already running."""
        await _shutdown_all(backends_list)
        while self._retiring:
            await asyncio.gather(*self._retiring, return_exceptions=True)

    async def shutdown_all(self) -> None:
        """Shut down all workspace backends, leased ones included. Called during server teardown.

        The registry is closed and emptied before any shutdown is awaited, so a concurrent call
        never resolves a workspace that is being shut down (a request queued on the lock raises
        instead of creating one), and a cancellation cannot leave one running. A backend a
        request still holds is stopped too: the server is going away, and a closed Pyright
        backend fails that request instead of restarting.
        """
        async with self._lock:
            self._closed = True
            popped = list(self._workspaces.values())
            self._workspaces.clear()
            self._known_roots.clear()
            self._auto_roots.clear()
            self._retire(popped)
            victims = [*popped, *(b for b in self._retired_live if b not in popped)]
            self._retired_live.clear()
            await _run_to_completion(self._stop_everything(victims))
