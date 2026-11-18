"""Unit tests for WorkspaceRegistry multi-workspace management."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from python_refactor_mcp.errors import AmbiguousWorkspaceError, ToolInputError, WorkspaceResolutionError
from python_refactor_mcp.workspace_registry import WorkspaceBackends, WorkspaceRegistry, _run_to_completion


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
    known_before = registry.get_known_roots()
    assert registry.resolve_workspace_root(target) == worktree
    assert registry.resolve_workspace_root(target) == worktree
    assert registry.get_known_roots() == known_before
    assert registry._auto_roots == set()


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
    assert registry.get_known_roots() == []
    assert registry._auto_roots == set()


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
    registry._auto_roots = {Path("/b")}

    await registry.shutdown_all()

    assert len(registry._workspaces) == 0
    assert len(registry._known_roots) == 0
    assert registry._auto_roots == set()
    backends_a.pyright.shutdown.assert_awaited_once()
    backends_b.pyright.shutdown.assert_awaited_once()


class _GatedShutdowns:
    """Makes every registered backend's Pyright shutdown wait on one gate and signal its entry."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    def gate(self, backends: WorkspaceBackends) -> None:
        async def _shutdown() -> None:
            self.entered.set()
            await self.release.wait()

        backends._initialized = True
        backends.pyright.shutdown.side_effect = _shutdown


@pytest.mark.asyncio
async def test_set_roots_cancelled_mid_shutdown_leaves_no_removed_workspace_registered() -> None:
    registry = WorkspaceRegistry()
    keep = Path("/keep").resolve()
    gates = _GatedShutdowns()
    removed = [_mock_backends(Path(name).resolve()) for name in ("/gone-a", "/gone-b")]
    for backends in removed:
        gates.gate(backends)
        registry._workspaces[backends.config.workspace_root] = backends
    registry._known_roots = [backends.config.workspace_root for backends in removed]

    task = asyncio.ensure_future(registry.set_roots([keep]))
    await gates.entered.wait()
    task.cancel()
    gates.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert registry._workspaces == {}
    assert registry.get_known_roots() == [keep]
    for backends in removed:
        backends.pyright.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_all_cancelled_mid_shutdown_stops_every_workspace_and_clears_roots() -> None:
    registry = WorkspaceRegistry()
    gates = _GatedShutdowns()
    workspaces = [_mock_backends(Path(name).resolve()) for name in ("/one", "/two")]
    for backends in workspaces:
        gates.gate(backends)
        registry._workspaces[backends.config.workspace_root] = backends
    registry._known_roots = [backends.config.workspace_root for backends in workspaces]
    registry._auto_roots = {workspaces[1].config.workspace_root}

    task = asyncio.ensure_future(registry.shutdown_all())
    await gates.entered.wait()
    task.cancel()
    gates.release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert registry._workspaces == {}
    assert registry._known_roots == []
    assert registry._auto_roots == set()
    for backends in workspaces:
        backends.pyright.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_path_less_call_never_resolves_a_workspace_that_shutdown_all_is_stopping() -> None:
    registry = WorkspaceRegistry()
    gates = _GatedShutdowns()
    only = _mock_backends(Path("/only").resolve())
    gates.gate(only)
    only.selected = True
    registry._workspaces[only.config.workspace_root] = only

    task = asyncio.ensure_future(registry.shutdown_all())
    await gates.entered.wait()
    with pytest.raises(AmbiguousWorkspaceError, match="no workspace is live"):
        registry.implicit_workspace()
    gates.release.set()
    await task


class _CleanupFailure(BaseException):
    """A non-Exception failure, which the cleanup coroutines do not swallow."""


@pytest.mark.asyncio
async def test_run_to_completion_reads_and_logs_a_cleanup_failure_when_cancelled(
    caplog: pytest.LogCaptureFixture,
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    inner: list[asyncio.Task[None]] = []

    async def _cleanup() -> None:
        task = asyncio.current_task()
        assert task is not None
        inner.append(task)
        entered.set()
        await release.wait()
        raise _CleanupFailure("cleanup blew up")

    outer = asyncio.ensure_future(_run_to_completion(_cleanup()))
    await entered.wait()
    outer.cancel()
    release.set()
    with caplog.at_level(logging.WARNING, logger="python_refactor_mcp.workspace_registry"), pytest.raises(
        asyncio.CancelledError
    ):
        await outer

    assert isinstance(inner[0].exception(), _CleanupFailure)
    failure_records = [r for r in caplog.records if "Cleanup task failed" in r.getMessage()]
    assert len(failure_records) == 1
    assert failure_records[0].exc_info is not None
    assert isinstance(failure_records[0].exc_info[1], _CleanupFailure)


# ── WorkspaceRegistry implicit workspace selection ───────────────────────


def _live(registry: WorkspaceRegistry, root: Path, *, selected: bool) -> WorkspaceBackends:
    """Register a live mocked workspace with the given selection state."""
    backends = _mock_backends(root)
    backends.selected = selected
    backends.last_accessed = 1.0
    registry._workspaces[root] = backends
    return backends


def test_implicit_workspace_rejects_an_empty_registry() -> None:
    with pytest.raises(AmbiguousWorkspaceError, match=r"no workspace is live.*root_path"):
        WorkspaceRegistry().implicit_workspace()


def test_implicit_workspace_returns_and_touches_the_sole_selected_workspace(tmp_path: Path) -> None:
    registry = WorkspaceRegistry()
    only = _live(registry, tmp_path / "only", selected=True)

    assert registry.implicit_workspace() is only
    assert only.last_accessed > 1.0


def test_implicit_workspace_rejects_a_sole_unselected_prewarmed_workspace(tmp_path: Path) -> None:
    registry = WorkspaceRegistry()
    warmed = _live(registry, tmp_path / "warmed", selected=False)

    with pytest.raises(AmbiguousWorkspaceError, match=r"pre-warmed, not selected.*root_path") as excinfo:
        registry.implicit_workspace()

    assert str(warmed.config.workspace_root) in str(excinfo.value)
    assert warmed.last_accessed == 1.0


def test_implicit_workspace_rejects_several_workspaces_naming_every_root(tmp_path: Path) -> None:
    registry = WorkspaceRegistry()
    first = tmp_path / "first"
    second = tmp_path / "second"
    _live(registry, first, selected=True)
    _live(registry, second, selected=True)

    with pytest.raises(AmbiguousWorkspaceError, match=r"2 workspaces are live.*root_path") as excinfo:
        registry.implicit_workspace()

    assert str(first) in str(excinfo.value)
    assert str(second) in str(excinfo.value)
    assert excinfo.value.code == "AMBIGUOUS_WORKSPACE"


def test_ambiguous_workspace_is_a_caller_input_error() -> None:
    assert issubclass(AmbiguousWorkspaceError, ToolInputError)


@pytest.mark.asyncio
async def test_prewarm_leaves_the_workspace_unselected_until_a_path_selects_it(tmp_path: Path) -> None:
    project = _marker_project(tmp_path, "project")
    registry = WorkspaceRegistry()

    with patch(
        "python_refactor_mcp.workspace_registry.discover_config", side_effect=lambda root: _mock_config(root)
    ), patch("python_refactor_mcp.workspace_registry.PyrightLSPClient", side_effect=lambda _c: AsyncMock()), \
         patch("python_refactor_mcp.workspace_registry.JediBackend"), \
         patch("python_refactor_mcp.workspace_registry.RopeBackend"):
        await registry.set_roots([project])
        warmed = await registry.prewarm(project)
        assert warmed.selected is False
        with pytest.raises(AmbiguousWorkspaceError, match="pre-warmed, not selected"):
            registry.implicit_workspace()

        selected = await registry.get_backends(str(project / "main.py"))

    assert selected is warmed
    assert selected.selected is True
    assert registry.implicit_workspace() is warmed


@pytest.mark.asyncio
async def test_evicted_selected_workspace_is_no_longer_implicit(tmp_path: Path) -> None:
    first = _marker_project(tmp_path, "first")
    second = _marker_project(tmp_path, "second")
    registry = WorkspaceRegistry(max_workspaces=1)

    with patch(
        "python_refactor_mcp.workspace_registry.discover_config", side_effect=lambda root: _mock_config(root)
    ), patch("python_refactor_mcp.workspace_registry.PyrightLSPClient", side_effect=lambda _c: AsyncMock()), \
         patch("python_refactor_mcp.workspace_registry.JediBackend"), \
         patch("python_refactor_mcp.workspace_registry.RopeBackend"):
        await registry.get_backends(str(first / "main.py"))
        await registry.prewarm(second)

    assert set(registry._workspaces) == {second}
    with pytest.raises(AmbiguousWorkspaceError, match="pre-warmed, not selected"):
        registry.implicit_workspace()


# ── Constructor validation ───────────────────────────────────────────────


def test_max_workspaces_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_workspaces must be >= 1"):
        WorkspaceRegistry(max_workspaces=0)


def test_registry_exposes_only_effective_lifecycle_settings() -> None:
    """The never-consumed idle timeout is gone; ``max_workspaces`` is the only setting."""
    assert set(inspect.signature(WorkspaceRegistry).parameters) == {"max_workspaces"}
    with pytest.raises(TypeError):
        WorkspaceRegistry(idle_timeout_seconds=1.0)  # type: ignore[call-arg]


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
    # Cancel 1 interrupts the hung start; cancel 2 interrupts the shield await and enters the
    # wait loop; cancel 3 interrupts that wait, which must keep waiting for the cleanup.
    for _ in range(3):
        task.cancel()
        await asyncio.sleep(0)
    assert cleaned == []
    assert not task.done()
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


# ── Eviction provenance ──────────────────────────────────────────────────


def _marker_project(parent: Path, name: str) -> Path:
    project = parent / name
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='test'\n")
    (project / "main.py").write_text("x = 1\n")
    return project.resolve()


@contextlib.contextmanager
def _patched_backends(make_pyright: Callable[[object], AsyncMock] | None = None) -> Iterator[None]:
    """Patch the backend constructors so a registry can initialize workspaces without real servers.

    ``make_pyright`` builds the Pyright client per workspace; the default is a bare AsyncMock.
    """
    with patch(
        "python_refactor_mcp.workspace_registry.discover_config", side_effect=lambda root: _mock_config(root)
    ), patch(
        "python_refactor_mcp.workspace_registry.PyrightLSPClient",
        side_effect=make_pyright or (lambda _c: AsyncMock()),
    ), \
         patch("python_refactor_mcp.workspace_registry.JediBackend"), \
         patch("python_refactor_mcp.workspace_registry.RopeBackend"):
        yield


def _initialized_workspaces(stamps: dict[Path, float]) -> dict[Path, WorkspaceBackends]:
    workspaces = {}
    for root, stamp in stamps.items():
        backends = _mock_backends(root)
        backends._initialized = True
        backends.last_accessed = stamp
        workspaces[root] = backends
    return workspaces


@pytest.mark.asyncio
async def test_evict_retains_older_explicit_root_over_newer_auto_root() -> None:
    registry = WorkspaceRegistry(max_workspaces=2)
    explicit = Path("/explicit").resolve()
    auto = Path("/auto").resolve()
    registry._known_roots = [explicit, auto]
    registry._auto_roots = {auto}
    registry._workspaces = _initialized_workspaces({explicit: 1.0, auto: 2.0})
    evicted = registry._workspaces[auto]

    await registry._evict_lru()

    assert set(registry._workspaces) == {explicit}
    evicted.pyright.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_evict_uses_lru_within_the_auto_class() -> None:
    registry = WorkspaceRegistry(max_workspaces=3)
    explicit, auto_old, auto_new = (Path(f"/{name}").resolve() for name in ("e", "ao", "an"))
    registry._known_roots = [explicit, auto_old, auto_new]
    registry._auto_roots = {auto_old, auto_new}
    registry._workspaces = _initialized_workspaces({explicit: 0.5, auto_old: 1.0, auto_new: 2.0})

    await registry._evict_lru()

    assert set(registry._workspaces) == {explicit, auto_new}


@pytest.mark.asyncio
async def test_evict_uses_lru_within_the_explicit_class() -> None:
    registry = WorkspaceRegistry(max_workspaces=2)
    old, new = Path("/old").resolve(), Path("/new").resolve()
    registry._known_roots = [old, new]
    registry._workspaces = _initialized_workspaces({old: 1.0, new: 2.0})

    await registry._evict_lru()

    assert set(registry._workspaces) == {new}


@pytest.mark.asyncio
async def test_get_backends_evicts_auto_discovered_workspace_before_explicit(tmp_path: Path) -> None:
    explicit = _marker_project(tmp_path, "explicit")
    auto_one = _marker_project(tmp_path, "auto_one")
    auto_two = _marker_project(tmp_path, "auto_two")
    registry = WorkspaceRegistry(max_workspaces=2)
    await registry.set_roots([explicit])

    with patch(
        "python_refactor_mcp.workspace_registry.discover_config",
        side_effect=lambda root: _mock_config(root),
    ), patch("python_refactor_mcp.workspace_registry.PyrightLSPClient", side_effect=lambda _c: AsyncMock()), \
         patch("python_refactor_mcp.workspace_registry.JediBackend"), \
         patch("python_refactor_mcp.workspace_registry.RopeBackend"):
        explicit_backends = await registry.get_backends(str(explicit / "main.py"))
        first_auto = await registry.get_backends(str(auto_one / "main.py"))
        explicit_backends.last_accessed = 1.0
        first_auto.last_accessed = 2.0
        await registry.get_backends(str(auto_two / "main.py"))

    assert set(registry._workspaces) == {explicit, auto_two}
    first_auto.pyright.shutdown.assert_awaited_once()
    assert {explicit, auto_one, auto_two} <= set(registry.get_known_roots())


@pytest.mark.asyncio
async def test_set_roots_promotes_auto_discovered_root_to_explicit(tmp_path: Path) -> None:
    promoted = _marker_project(tmp_path, "promoted")
    other = _marker_project(tmp_path, "other")
    registry = WorkspaceRegistry(max_workspaces=2)
    with _patched_backends():
        await registry.get_backends(str(promoted / "main.py"))
    assert promoted in registry._auto_roots
    await registry.set_roots([promoted])
    assert registry._auto_roots == set()
    with _patched_backends():
        await registry.get_backends(str(other / "main.py"))
    assert registry._auto_roots == {other}
    registry._workspaces = _initialized_workspaces({promoted: 1.0, other: 2.0})

    await registry._evict_lru()

    assert set(registry._workspaces) == {promoted}


# ── Root discovery is registered on dispatch, after a successful start ───


@pytest.mark.asyncio
async def test_get_backends_registers_a_discovered_root_after_initialize(tmp_path: Path) -> None:
    project = _marker_project(tmp_path, "project")
    registry = WorkspaceRegistry()
    seen_during_start: list[list[Path]] = []

    def make_pyright(_config: object) -> AsyncMock:
        pyright = AsyncMock()

        async def start() -> None:
            seen_during_start.append(registry.get_known_roots())

        pyright.start.side_effect = start
        return pyright

    with _patched_backends(make_pyright):
        await registry.get_backends(str(project / "main.py"))

    assert seen_during_start == [[]]
    assert registry.get_known_roots() == [project]
    assert registry._auto_roots == {project}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["pyright_start", "discover_config"])
async def test_failed_initialize_leaves_no_root_registered(tmp_path: Path, failure: str) -> None:
    project = _marker_project(tmp_path, "project")
    registry = WorkspaceRegistry()

    def make_pyright(_config: object) -> AsyncMock:
        pyright = AsyncMock()
        if failure == "pyright_start":
            pyright.start.side_effect = RuntimeError("pyright failed")
        return pyright

    def make_config(root: Path) -> MagicMock:
        if failure == "discover_config":
            raise RuntimeError("config failed")
        return _mock_config(root)

    with patch("python_refactor_mcp.workspace_registry.discover_config", side_effect=make_config), \
         patch("python_refactor_mcp.workspace_registry.PyrightLSPClient", side_effect=make_pyright), \
         patch("python_refactor_mcp.workspace_registry.JediBackend"), \
         patch("python_refactor_mcp.workspace_registry.RopeBackend"), pytest.raises(RuntimeError, match="failed"):
        await registry.get_backends(str(project / "main.py"))

    assert registry.get_known_roots() == []
    assert registry._auto_roots == set()
    assert registry.active_backends() == []


@pytest.mark.asyncio
async def test_prewarm_registers_the_discovered_root_unselected(tmp_path: Path) -> None:
    project = _marker_project(tmp_path, "project")
    registry = WorkspaceRegistry()

    with _patched_backends():
        warmed = await registry.prewarm(project)

    assert warmed.selected is False
    assert registry.get_known_roots() == [project]
    assert registry._auto_roots == {project}


@pytest.mark.asyncio
async def test_resolving_during_a_slow_start_reads_without_mutating(tmp_path: Path) -> None:
    project = _marker_project(tmp_path, "project")
    registry = WorkspaceRegistry()
    entered = asyncio.Event()
    gate = asyncio.Event()

    def make_pyright(_config: object) -> AsyncMock:
        pyright = AsyncMock()

        async def start() -> None:
            entered.set()
            await gate.wait()

        pyright.start.side_effect = start
        return pyright

    with _patched_backends(make_pyright):
        task = asyncio.create_task(registry.get_backends(str(project / "main.py")))
        await entered.wait()
        assert registry.resolve_workspace_root(project / "main.py") == project
        assert registry.get_known_roots() == []
        gate.set()
        await task

    assert registry.get_known_roots() == [project]


@pytest.mark.asyncio
async def test_spanning_calls_register_each_root_once(tmp_path: Path) -> None:
    first = _marker_project(tmp_path, "first")
    second = _marker_project(tmp_path, "second")
    registry = WorkspaceRegistry(max_workspaces=3)

    with _patched_backends():
        await registry.get_backends(str(first / "main.py"))
        await registry.get_backends(str(second / "main.py"))
        await registry.get_backends(str(first / "main.py"))

    assert registry.get_known_roots() == [first, second]
    assert registry._auto_roots == {first, second}


@pytest.mark.asyncio
async def test_explicit_root_is_never_reclassified_as_auto_on_dispatch(tmp_path: Path) -> None:
    project = _marker_project(tmp_path, "project")
    registry = WorkspaceRegistry()
    await registry.set_roots([project])

    with _patched_backends():
        await registry.get_backends(str(project / "main.py"))

    assert registry.get_known_roots() == [project]
    assert registry._auto_roots == set()
