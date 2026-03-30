"""Dynamic multi-workspace backend registry with lazy init and LRU eviction."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from python_refactor_mcp.backends.jedi_backend import JediBackend
from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient
from python_refactor_mcp.backends.rope_backend import RopeBackend
from python_refactor_mcp.config import ServerConfig, discover_config
from python_refactor_mcp.errors import WorkspaceResolutionError

_LOGGER = logging.getLogger(__name__)

# Project markers used to discover workspace roots by walking parent directories.
_PROJECT_MARKERS = (".git", "pyproject.toml", "setup.py", "setup.cfg")


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
    _initialized: bool = field(default=False, repr=False)

    async def initialize(self) -> None:
        """Start all three backends for this workspace."""
        if self._initialized:
            return
        await self.pyright.start()
        self.jedi.initialize()
        self.rope.initialize()
        self._initialized = True

    async def shutdown(self) -> None:
        """Stop all backends, releasing subprocess and file handles."""
        if not self._initialized:
            return
        self._initialized = False
        try:
            await self.pyright.shutdown()
        except Exception:
            _LOGGER.warning("Pyright shutdown failed for %s", self.config.workspace_root, exc_info=True)
        try:
            self.rope.close()
        except Exception:
            _LOGGER.warning("Rope close failed for %s", self.config.workspace_root, exc_info=True)

    def touch(self) -> None:
        """Update last-accessed timestamp for LRU tracking."""
        self.last_accessed = time.monotonic()


class WorkspaceRegistry:
    """Manages per-workspace backend instances with lazy init and LRU eviction.

    Thread safety: all mutations are guarded by an asyncio.Lock.
    """

    def __init__(
        self,
        max_workspaces: int = 3,
        idle_timeout_seconds: float = 600.0,
    ) -> None:
        if max_workspaces < 1:
            raise ValueError("max_workspaces must be >= 1")
        self._max_workspaces = max_workspaces
        self._idle_timeout = idle_timeout_seconds
        self._workspaces: dict[Path, WorkspaceBackends] = {}
        self._known_roots: list[Path] = []
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
        """Resolve workspace for *file_path*, lazily initialize, and return backends.

        This is the hot path — called on every tool invocation that has a
        file_path parameter.
        """
        resolved_file = Path(file_path).resolve()
        root = self.resolve_workspace_root(resolved_file)

        async with self._lock:
            existing = self._workspaces.get(root)
            if existing is not None:
                existing.touch()
                return existing

            await self._evict_lru()
            backends = await self._initialize_workspace(root)
            return backends

    def get_most_recent(self) -> WorkspaceBackends | None:
        """Return the most recently accessed workspace, or None if empty.

        Used as fallback for tools without a file_path parameter.
        """
        if not self._workspaces:
            return None
        return max(self._workspaces.values(), key=lambda b: b.last_accessed)

    # ── Workspace resolution ─────────────────────────────────────────────

    def resolve_workspace_root(self, file_path: Path) -> Path:
        """Map a file path to its workspace root.

        Resolution order:
        1. Longest-prefix match against known roots (handles nested workspaces)
        2. Walk parent directories looking for project markers
        3. Raise WorkspaceResolutionError if nothing found
        """
        resolved = file_path.resolve()

        # 1. Longest-prefix match against known roots.
        best_match: Path | None = None
        best_depth = -1
        for root in self._known_roots:
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            depth = len(root.parts)
            if depth > best_depth:
                best_depth = depth
                best_match = root

        if best_match is not None:
            return best_match

        # 2. Walk parent directories for project markers.
        for parent in resolved.parents:
            for marker in _PROJECT_MARKERS:
                if (parent / marker).exists():
                    # Auto-register discovered root.
                    if parent not in self._known_roots:
                        self._known_roots.append(parent)
                        _LOGGER.info("Auto-discovered workspace root: %s (marker: %s)", parent, marker)
                    return parent

        raise WorkspaceResolutionError(
            f"Cannot determine workspace root for: {file_path}. "
            f"No project markers ({', '.join(_PROJECT_MARKERS)}) found in parent directories, "
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

    async def _evict_lru(self) -> None:
        """Evict the least-recently-used workspace if at capacity. Caller must hold _lock."""
        if len(self._workspaces) < self._max_workspaces:
            return

        # Prefer evicting auto-discovered roots over explicit roots.
        explicit_roots = set(self._known_roots)
        candidates = sorted(
            self._workspaces.items(),
            key=lambda kv: (kv[0] in explicit_roots, kv[1].last_accessed),
        )
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
