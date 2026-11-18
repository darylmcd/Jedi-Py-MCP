"""Unit tests for WorkspaceRegistry multi-workspace management."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from python_refactor_mcp.errors import WorkspaceResolutionError
from python_refactor_mcp.workspace_registry import WorkspaceBackends, WorkspaceRegistry


def _mock_config(root: Path) -> MagicMock:
    """Create a mock ServerConfig with workspace_root set."""
    config = MagicMock()
    config.workspace_root = root
    return config


def _mock_backends(root: Path) -> WorkspaceBackends:
    """Create a WorkspaceBackends with mocked backend instances."""
    config = _mock_config(root)
    pyright = AsyncMock()
    jedi = MagicMock()
    rope = MagicMock()
    return WorkspaceBackends(config=config, pyright=pyright, jedi=jedi, rope=rope)


# ── WorkspaceBackends lifecycle ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_starts_all_backends() -> None:
    backends = _mock_backends(Path("/project"))
    await backends.initialize()

    backends.pyright.start.assert_awaited_once()
    backends.jedi.initialize.assert_called_once()
    backends.rope.initialize.assert_called_once()
    assert backends._initialized is True


@pytest.mark.asyncio
async def test_initialize_is_idempotent() -> None:
    backends = _mock_backends(Path("/project"))
    await backends.initialize()
    await backends.initialize()

    backends.pyright.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_stops_backends() -> None:
    backends = _mock_backends(Path("/project"))
    await backends.initialize()
    await backends.shutdown()

    backends.pyright.shutdown.assert_awaited_once()
    backends.rope.close.assert_called_once()
    assert backends._initialized is False


@pytest.mark.asyncio
async def test_shutdown_without_init_is_noop() -> None:
    backends = _mock_backends(Path("/project"))
    await backends.shutdown()

    backends.pyright.shutdown.assert_not_awaited()


def test_touch_updates_timestamp() -> None:
    backends = _mock_backends(Path("/project"))
    old = backends.last_accessed
    backends.touch()
    assert backends.last_accessed >= old


# ── WorkspaceRegistry resolution ─────────────────────────────────────────


def test_resolve_known_root(tmp_path: Path) -> None:
    registry = WorkspaceRegistry()
    root = tmp_path / "project"
    root.mkdir()
    registry._known_roots = [root]

    result = registry.resolve_workspace_root(root / "src" / "main.py")
    assert result == root


def test_resolve_longest_prefix_match(tmp_path: Path) -> None:
    outer = tmp_path / "mono"
    inner = tmp_path / "mono" / "packages" / "core"
    outer.mkdir(parents=True)
    inner.mkdir(parents=True)

    registry = WorkspaceRegistry()
    registry._known_roots = [outer, inner]

    result = registry.resolve_workspace_root(inner / "src" / "main.py")
    assert result == inner


@pytest.mark.parametrize("known_outer", [False, True])
@pytest.mark.parametrize("resolve_directory", [False, True])
def test_resolve_nested_worktree(
    tmp_path: Path, known_outer: bool, resolve_directory: bool
) -> None:
    outer = tmp_path / "primary"
    worktree = outer / ".worktrees" / "branch"
    worktree.mkdir(parents=True)
    (outer / "pyproject.toml").touch()
    (worktree / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    (worktree / "pyproject.toml").touch()
    module = worktree / "module.py"
    module.touch()
    registry = WorkspaceRegistry()
    if known_outer:
        registry._known_roots = [outer]

    target = worktree if resolve_directory else module
    assert registry.resolve_workspace_root(target) == worktree
    assert registry.get_known_roots().count(worktree) == 1
    assert registry.resolve_workspace_root(target) == worktree
    assert registry.get_known_roots().count(worktree) == 1


def test_resolve_unregistered_project_directory(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "setup.cfg").touch()

    assert WorkspaceRegistry().resolve_workspace_root(root) == root


def test_resolve_nested_project_marker_under_known_git_root(tmp_path: Path) -> None:
    project = tmp_path / "packages" / "project"
    project.mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    (project / "pyproject.toml").touch()
    registry = WorkspaceRegistry()
    registry._known_roots = [tmp_path]

    assert registry.resolve_workspace_root(project / "module.py") == project


def test_resolve_exact_known_root_before_ancestor_marker(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").touch()
    root = tmp_path / "not-created-yet"
    registry = WorkspaceRegistry()
    registry._known_roots = [root]

    assert registry.resolve_workspace_root(root) == root
    assert registry.resolve_workspace_root(root / "module.py") == root


def test_resolve_walks_parents_for_markers(tmp_path: Path) -> None:
    project_root = tmp_path / "my_project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='test'\n")
    nested_file = project_root / "src" / "deep" / "module.py"
    nested_file.parent.mkdir(parents=True)
    nested_file.touch()

    registry = WorkspaceRegistry()
    result = registry.resolve_workspace_root(nested_file)

    assert result == project_root
    assert project_root in registry._known_roots


def test_resolve_walks_parents_for_git(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / ".git").mkdir()
    nested_file = project_root / "src" / "main.py"
    nested_file.parent.mkdir(parents=True)
    nested_file.touch()

    registry = WorkspaceRegistry()
    result = registry.resolve_workspace_root(nested_file)
    assert result == project_root


def test_resolve_raises_when_no_root_found(tmp_path: Path) -> None:
    registry = WorkspaceRegistry()
    # tmp_path has no project markers and is not a known root
    orphan = tmp_path / "orphan.py"
    orphan.touch()

    with pytest.raises(WorkspaceResolutionError, match="Cannot determine workspace root"):
        registry.resolve_workspace_root(orphan)


# ── WorkspaceRegistry get_backends ───────────────────────────────────────


@pytest.mark.asyncio
async def test_get_backends_creates_and_caches(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='test'\n")
    src = project / "main.py"
    src.write_text("x = 1\n")

    registry = WorkspaceRegistry()

    with patch("python_refactor_mcp.workspace_registry.discover_config") as mock_config, \
         patch("python_refactor_mcp.workspace_registry.PyrightLSPClient") as mock_pyright, \
         patch("python_refactor_mcp.workspace_registry.JediBackend"), \
         patch("python_refactor_mcp.workspace_registry.RopeBackend"):
        mock_config.return_value = _mock_config(project)
        mock_pyright_inst = AsyncMock()
        mock_pyright.return_value = mock_pyright_inst

        backends1 = await registry.get_backends(str(src))
        backends2 = await registry.get_backends(str(src))

    assert backends1 is backends2
    mock_config.assert_called_once()


# ── WorkspaceRegistry set_roots ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_roots_shuts_down_removed() -> None:
    registry = WorkspaceRegistry()
    root_a = Path("/a").resolve()
    root_b = Path("/b").resolve()

    backends_a = _mock_backends(root_a)
    backends_a._initialized = True
    registry._workspaces[root_a] = backends_a
    registry._known_roots = [root_a, root_b]

    await registry.set_roots([root_b])

    assert root_a not in registry._workspaces
    backends_a.pyright.shutdown.assert_awaited_once()


# ── WorkspaceRegistry eviction ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_evict_lru_removes_oldest(tmp_path: Path) -> None:
    registry = WorkspaceRegistry(max_workspaces=2)

    root_a = Path("/a").resolve()
    root_b = Path("/b").resolve()

    backends_a = _mock_backends(root_a)
    backends_a._initialized = True
    backends_a.last_accessed = 1.0

    backends_b = _mock_backends(root_b)
    backends_b._initialized = True
    backends_b.last_accessed = 2.0

    registry._workspaces = {root_a: backends_a, root_b: backends_b}

    await registry._evict_lru()

    assert root_a not in registry._workspaces
    assert root_b in registry._workspaces
    backends_a.pyright.shutdown.assert_awaited_once()


# ── WorkspaceRegistry shutdown_all ───────────────────────────────────────


@pytest.mark.asyncio
async def test_shutdown_all() -> None:
    registry = WorkspaceRegistry()

    backends_a = _mock_backends(Path("/a"))
    backends_a._initialized = True
    backends_b = _mock_backends(Path("/b"))
    backends_b._initialized = True

    registry._workspaces = {Path("/a"): backends_a, Path("/b"): backends_b}
    registry._known_roots = [Path("/a"), Path("/b")]

    await registry.shutdown_all()

    assert len(registry._workspaces) == 0
    assert len(registry._known_roots) == 0
    backends_a.pyright.shutdown.assert_awaited_once()
    backends_b.pyright.shutdown.assert_awaited_once()


# ── WorkspaceRegistry get_most_recent ────────────────────────────────────


def test_get_most_recent_returns_none_when_empty() -> None:
    registry = WorkspaceRegistry()
    assert registry.get_most_recent() is None


def test_get_most_recent_returns_latest() -> None:
    registry = WorkspaceRegistry()
    old = _mock_backends(Path("/old"))
    old.last_accessed = 1.0
    new = _mock_backends(Path("/new"))
    new.last_accessed = 2.0
    registry._workspaces = {Path("/old"): old, Path("/new"): new}

    assert registry.get_most_recent() is new


# ── Constructor validation ───────────────────────────────────────────────


def test_max_workspaces_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_workspaces must be >= 1"):
        WorkspaceRegistry(max_workspaces=0)


# ── Startup rollback ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_failure_after_pyright_start_reaps_pyright_and_rope() -> None:
    backends = _mock_backends(Path("/project"))
    backends.jedi.initialize.side_effect = RuntimeError("jedi failed")

    with pytest.raises(RuntimeError, match="jedi failed"):
        await backends.initialize()

    backends.pyright.shutdown.assert_awaited_once()
    backends.rope.close.assert_called_once()
    assert backends.is_initialized is False
    await backends.shutdown()
    backends.pyright.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_rope_initialize_failure_reaps_pyright() -> None:
    backends = _mock_backends(Path("/project"))
    backends.rope.initialize.side_effect = RuntimeError("rope failed")

    with pytest.raises(RuntimeError, match="rope failed"):
        await backends.initialize()

    backends.pyright.shutdown.assert_awaited_once()
    backends.rope.close.assert_called_once()
    assert backends.is_initialized is False


@pytest.mark.asyncio
async def test_pyright_start_failure_runs_cleanup() -> None:
    backends = _mock_backends(Path("/project"))
    backends.pyright.start.side_effect = RuntimeError("pyright failed")

    with pytest.raises(RuntimeError, match="pyright failed"):
        await backends.initialize()

    backends.pyright.shutdown.assert_awaited_once()
    backends.rope.close.assert_called_once()
    backends.jedi.initialize.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_mask_startup_error() -> None:
    backends = _mock_backends(Path("/project"))
    backends.rope.initialize.side_effect = RuntimeError("rope failed")
    backends.pyright.shutdown.side_effect = OSError("cannot terminate")

    with pytest.raises(RuntimeError, match="rope failed"):
        await backends.initialize()

    backends.rope.close.assert_called_once()


@pytest.mark.asyncio
async def test_cancelled_startup_still_reaps_pyright() -> None:
    backends = _mock_backends(Path("/project"))
    started = asyncio.Event()

    async def hang() -> None:
        started.set()
        await asyncio.Event().wait()

    backends.pyright.start.side_effect = hang
    task = asyncio.create_task(backends.initialize())
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    backends.pyright.shutdown.assert_awaited_once()
    backends.rope.close.assert_called_once()
    assert backends.is_initialized is False


@pytest.mark.asyncio
async def test_repeated_cancellation_does_not_drop_startup_cleanup() -> None:
    backends = _mock_backends(Path("/project"))
    started = asyncio.Event()
    gate = asyncio.Event()
    cleaned: list[bool] = []

    async def hang() -> None:
        started.set()
        await asyncio.Event().wait()

    async def slow_shutdown() -> None:
        await gate.wait()
        cleaned.append(True)

    backends.pyright.start.side_effect = hang
    backends.pyright.shutdown.side_effect = slow_shutdown
    task = asyncio.create_task(backends.initialize())
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    gate.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert cleaned == [True]
    backends.rope.close.assert_called_once()


@pytest.mark.asyncio
async def test_cancelled_shutdown_still_closes_rope_and_finishes_pyright() -> None:
    backends = _mock_backends(Path("/project"))
    await backends.initialize()
    entered = asyncio.Event()
    gate = asyncio.Event()
    finished: list[bool] = []

    async def slow_shutdown() -> None:
        entered.set()
        await gate.wait()
        finished.append(True)

    backends.pyright.shutdown.side_effect = slow_shutdown
    task = asyncio.create_task(backends.shutdown())
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    gate.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert finished == [True]
    backends.rope.close.assert_called_once()
    assert backends.is_initialized is False


@pytest.mark.asyncio
async def test_failed_workspace_startup_is_cleaned_up_and_retryable(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='test'\n")
    source = project / "main.py"
    source.write_text("x = 1\n")
    registry = WorkspaceRegistry(max_workspaces=1)
    pyrights: list[AsyncMock] = []
    jedis: list[MagicMock] = []

    def make_pyright(_config: object) -> AsyncMock:
        pyrights.append(AsyncMock())
        return pyrights[-1]

    def make_jedi(_config: object) -> MagicMock:
        jedis.append(MagicMock())
        if len(jedis) == 1:
            jedis[-1].initialize.side_effect = RuntimeError("jedi failed")
        return jedis[-1]

    with patch("python_refactor_mcp.workspace_registry.discover_config") as mock_config, \
         patch("python_refactor_mcp.workspace_registry.PyrightLSPClient", side_effect=make_pyright), \
         patch("python_refactor_mcp.workspace_registry.JediBackend", side_effect=make_jedi), \
         patch("python_refactor_mcp.workspace_registry.RopeBackend"):
        mock_config.return_value = _mock_config(project)

        with pytest.raises(RuntimeError, match="jedi failed"):
            await registry.get_backends(str(source))
        assert registry.active_backends() == []
        pyrights[0].shutdown.assert_awaited_once()

        recovered = await registry.get_backends(str(source))
        again = await registry.get_backends(str(source))

    assert recovered is again
    assert recovered.is_initialized
    assert len(pyrights) == 2
    pyrights[1].shutdown.assert_not_awaited()
