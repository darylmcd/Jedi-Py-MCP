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
    so a second cancellation cannot drop the only reference to it.
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
        raise


@dataclass
class WorkspaceBackends:
    """Per-workspace backend triad with lifecycle management.

    Field names (pyright, jedi, rope, config) intentionally mirror the old
    AppContext so that tool functions work unchanged after the switch.
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
        self._lock = asyncio.Lock()

    # ── Root management ──────────────────────────────────────────────────

    async def set_roots(self, roots: list[Path]) -> None:
        """Update the set of known workspace roots.

        Shuts down backends for any roots that were removed.
        Does NOT eagerly initialize new roots (lazy on first tool call).
        """
        resolved = [r.resolve() for r in roots]
        async with self._lock:
            old_set = set(self._known_roots)
            new_set = set(resolved)
            removed = old_set - new_set

            self._known_roots = resolved
            # Every root passed here is explicit, including one previously auto-discovered.
            self._auto_roots.clear()

            for root in removed:
                backends = self._workspaces.pop(root, None)
                if backends is not None:
                    _LOGGER.info("Shutting down removed workspace: %s", root)
                    await backends.shutdown()

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
        """
        root = self.resolve_workspace_root(Path(file_path).resolve())
        backends = await self._get_or_create(root)
        backends.selected = True
        return backends

    async def prewarm(self, root: Path) -> WorkspaceBackends:
        """Start the workspace enclosing *root* without selecting it.

        Used for the startup pre-warm: the backends are ready, but a path-less call
        still has to name its workspace (see :meth:`implicit_workspace`).
        """
        return await self._get_or_create(self.resolve_workspace_root(root.resolve()))

    async def _get_or_create(self, root: Path) -> WorkspaceBackends:
        """Return the live backends of *root*, evicting and initializing as needed."""
        async with self._lock:
            existing = self._workspaces.get(root)
            if existing is not None:
                existing.touch()
                return existing

            await self._evict_lru()
            return await self._initialize_workspace(root)

    def implicit_workspace(self) -> WorkspaceBackends:
        """Return the workspace a call that names no path means, or raise when that is not unambiguous.

        Only a sole live workspace that a path-bearing request already selected qualifies;
        it is touched so the LRU sees the use. Several live workspaces, a pre-warmed root no
        request has selected, and an empty registry raise :class:`AmbiguousWorkspaceError`
        naming the live roots and the ``root_path`` parameter.
        """
        live = self.active_backends()
        if len(live) == 1 and live[0].selected:
            live[0].touch()
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
        """Return the deepest known root or project marker enclosing a path."""
        resolved = file_path.resolve()
        if resolved in self._known_roots:
            return resolved

        directory = resolved if resolved.is_dir() else resolved.parent
        for parent in (directory, *directory.parents):
            if parent in self._known_roots:
                return parent
            for marker in _PROJECT_MARKERS:
                if (parent / marker).exists():
                    self._known_roots.append(parent)
                    self._auto_roots.add(parent)
                    _LOGGER.info("Auto-discovered workspace root: %s (marker: %s)", parent, marker)
                    return parent

        raise WorkspaceResolutionError(
            f"Cannot determine workspace root for: {file_path}. "
            f"No project markers ({', '.join(_PROJECT_MARKERS)}) found in enclosing directories, "
            f"and the path is not under any known root."
        )

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def _initialize_workspace(self, root: Path) -> WorkspaceBackends:
        """Create and start backends for a workspace root. Caller must hold _lock."""
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
        return backends

    def _eviction_key(self, root: Path, backends: WorkspaceBackends) -> tuple[bool, float]:
        """Sort key for eviction; the smallest key is evicted first.

        Auto-discovered roots go before explicit ones; least recently used first within each class.
        """
        return (root not in self._auto_roots, backends.last_accessed)

    async def _evict_lru(self) -> None:
        """Evict the least-recently-used workspace if at capacity. Caller must hold _lock."""
        if len(self._workspaces) < self._max_workspaces:
            return

        candidates = sorted(self._workspaces.items(), key=lambda kv: self._eviction_key(*kv))
        evict_root, evict_backends = candidates[0]
        _LOGGER.info("Evicting LRU workspace: %s (last_accessed=%.1f)", evict_root, evict_backends.last_accessed)
        del self._workspaces[evict_root]
        await evict_backends.shutdown()

    async def shutdown_all(self) -> None:
        """Shut down all workspace backends. Called during server teardown."""
        async with self._lock:
            for root, backends in list(self._workspaces.items()):
                _LOGGER.info("Shutting down workspace: %s", root)
                await backends.shutdown()
            self._workspaces.clear()
            self._known_roots.clear()
            self._auto_roots.clear()
