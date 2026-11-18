"""Unit tests for workspace leases: a backend stays alive through dispatch, then is retired.

Every ordering below is driven by events and task yields, never by sleeps.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import Callable, Coroutine, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from python_refactor_mcp import tool_runtime
from python_refactor_mcp.backends._threading import run_in_thread
from python_refactor_mcp.errors import PyrightError, RopeError, ToolInputError, WorkspaceResolutionError
from python_refactor_mcp.tool_runtime import MultiWorkspaceContext, get_current_backends, tool_error_boundary
from python_refactor_mcp.workspace_registry import WorkspaceBackends, WorkspaceRegistry


class _CleanupFailure(BaseException):
    """A non-Exception failure, which the backend cleanup does not swallow."""


def _project(parent: Path, name: str) -> Path:
    project = parent / name
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='test'\n")
    (project / "main.py").write_text("x = 1\n")
    return project.resolve()


def _source(project: Path) -> str:
    return str(project / "main.py")


class _World:
    """Patched backend constructors that record one Pyright mock per workspace start."""

    def __init__(self) -> None:
        self.pyrights: list[tuple[Path, AsyncMock]] = []

    def pyright(self, root: Path) -> AsyncMock:
        """Return the most recently created Pyright mock of *root*."""
        return next(mock for created, mock in reversed(self.pyrights) if created == root)

    def make_pyright(self, config: MagicMock) -> AsyncMock:
        mock = AsyncMock()
        self.pyrights.append((config.workspace_root, mock))
        return mock

    @contextlib.contextmanager
    def patched(self) -> Iterator[None]:
        def make_config(root: Path) -> MagicMock:
            config = MagicMock()
            config.workspace_root = root
            return config

        with patch("python_refactor_mcp.workspace_registry.discover_config", side_effect=make_config), \
             patch("python_refactor_mcp.workspace_registry.PyrightLSPClient", side_effect=self.make_pyright), \
             patch("python_refactor_mcp.workspace_registry.JediBackend"), \
             patch("python_refactor_mcp.workspace_registry.RopeBackend"):
            yield


@pytest.fixture
def world() -> Iterator[_World]:
    state = _World()
    with state.patched():
        yield state


async def _settle(registry: WorkspaceRegistry) -> None:
    """Wait for every deferred shutdown the registry started."""
    await asyncio.gather(*registry._retiring)


def _gate_shutdown(pyright: AsyncMock) -> tuple[asyncio.Event, asyncio.Event]:
    """Make *pyright*'s shutdown block; returns (entered, release)."""
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocked() -> None:
        entered.set()
        await release.wait()

    pyright.shutdown.side_effect = blocked
    return entered, release


# -- Eviction defers the shutdown of a leased workspace ---------------------


@pytest.mark.asyncio
async def test_evicting_a_leased_workspace_defers_its_shutdown_until_release(
    tmp_path: Path, world: _World
) -> None:
    first = _project(tmp_path, "first")
    second = _project(tmp_path, "second")
    registry = WorkspaceRegistry(max_workspaces=1)

    held = await registry.get_backends(_source(first))
    await registry.get_backends(_source(second))

    assert [b.config.workspace_root for b in registry.active_backends()] == [second]
    world.pyright(first).shutdown.assert_not_awaited()

    registry.release(held)
    await _settle(registry)

    world.pyright(first).shutdown.assert_awaited_once()
    assert held.is_initialized is False


@pytest.mark.asyncio
async def test_an_evicted_root_requested_again_gets_fresh_backends(tmp_path: Path, world: _World) -> None:
    first = _project(tmp_path, "first")
    second = _project(tmp_path, "second")
    registry = WorkspaceRegistry(max_workspaces=1)
    held = await registry.get_backends(_source(first))
    await registry.get_backends(_source(second))

    again = await registry.get_backends(_source(first))

    assert again is not held
    assert held.leases == 1  # no lease ever lands on a backend the registry dropped
    assert again.leases == 1


@pytest.mark.asyncio
async def test_evicting_an_idle_workspace_still_shuts_it_down_at_once(tmp_path: Path, world: _World) -> None:
    first = _project(tmp_path, "first")
    second = _project(tmp_path, "second")
    registry = WorkspaceRegistry(max_workspaces=1)
    registry.release(await registry.get_backends(_source(first)))

    await registry.get_backends(_source(second))

    world.pyright(first).shutdown.assert_awaited_once()
    assert not registry._retiring


@pytest.mark.asyncio
async def test_a_new_root_is_not_held_back_by_a_leased_workspace_at_capacity(
    tmp_path: Path, world: _World
) -> None:
    first = _project(tmp_path, "first")
    second = _project(tmp_path, "second")
    registry = WorkspaceRegistry(max_workspaces=1)
    held = await registry.get_backends(_source(first))

    task = asyncio.ensure_future(registry.get_backends(_source(second)))
    for _ in range(5):
        await asyncio.sleep(0)

    assert task.done()
    world.pyright(second).start.assert_awaited_once()
    registry.release(held)
    registry.release(await task)
    await _settle(registry)


@pytest.mark.asyncio
async def test_a_request_for_a_leased_workspace_does_not_block(tmp_path: Path, world: _World) -> None:
    project = _project(tmp_path, "project")
    registry = WorkspaceRegistry(max_workspaces=1)
    first = await registry.get_backends(_source(project))

    task = asyncio.ensure_future(registry.get_backends(_source(project)))
    for _ in range(5):
        await asyncio.sleep(0)

    assert task.done()
    second = task.result()
    assert second is first
    assert first.leases == 2
    registry.release(first)
    registry.release(second)
    assert first.leases == 0


# -- Lease bookkeeping -------------------------------------------------------


@pytest.mark.asyncio
async def test_prewarm_takes_no_lease_and_implicit_workspace_takes_one(tmp_path: Path, world: _World) -> None:
    project = _project(tmp_path, "project")
    registry = WorkspaceRegistry()

    warmed = await registry.prewarm(project)
    assert warmed.leases == 0
    assert warmed.selected is False

    registry.release(await registry.get_backends(_source(project)))
    implicit = registry.implicit_workspace()
    assert implicit.leases == 1
    registry.release(implicit)
    assert implicit.leases == 0


@pytest.mark.asyncio
async def test_releasing_more_often_than_acquired_is_a_defect(tmp_path: Path, world: _World) -> None:
    registry = WorkspaceRegistry()
    backends = await registry.get_backends(_source(_project(tmp_path, "project")))
    registry.release(backends)

    with pytest.raises(RuntimeError, match="released more often than acquired"):
        registry.release(backends)


# -- set_roots ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_roots_defers_the_shutdown_of_a_removed_leased_root(tmp_path: Path, world: _World) -> None:
    kept = _project(tmp_path, "kept")
    removed = _project(tmp_path, "removed")
    registry = WorkspaceRegistry()
    await registry.set_roots([kept, removed])
    held = await registry.get_backends(_source(removed))
    idle = await registry.get_backends(_source(kept))
    registry.release(idle)

    await registry.set_roots([kept])

    assert [b.config.workspace_root for b in registry.active_backends()] == [kept]
    world.pyright(removed).shutdown.assert_not_awaited()
    registry.release(held)
    await _settle(registry)
    world.pyright(removed).shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_roots_shuts_a_removed_idle_root_down_before_returning(tmp_path: Path, world: _World) -> None:
    kept = _project(tmp_path, "kept")
    removed = _project(tmp_path, "removed")
    registry = WorkspaceRegistry()
    await registry.set_roots([kept, removed])
    registry.release(await registry.get_backends(_source(removed)))

    await registry.set_roots([kept])

    world.pyright(removed).shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_roots_cancelled_mid_shutdown_still_retires_a_leased_root(
    tmp_path: Path, world: _World
) -> None:
    idle_root = _project(tmp_path, "idle")
    leased_root = _project(tmp_path, "leased")
    registry = WorkspaceRegistry()
    await registry.set_roots([idle_root, leased_root])
    registry.release(await registry.get_backends(_source(idle_root)))
    held = await registry.get_backends(_source(leased_root))
    entered, release = _gate_shutdown(world.pyright(idle_root))

    task = asyncio.ensure_future(registry.set_roots([]))
    await entered.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    world.pyright(leased_root).shutdown.assert_not_awaited()
    registry.release(held)
    await _settle(registry)
    world.pyright(leased_root).shutdown.assert_awaited_once()


# -- shutdown_all -------------------------------------------------------------


@pytest.mark.asyncio
async def test_shutdown_all_stops_a_leased_workspace_without_waiting_for_its_holder(
    tmp_path: Path, world: _World
) -> None:
    project = _project(tmp_path, "project")
    registry = WorkspaceRegistry()
    held = await registry.get_backends(_source(project))

    await registry.shutdown_all()

    world.pyright(project).shutdown.assert_awaited_once()
    registry.release(held)  # a late release after the forced shutdown starts nothing
    assert not registry._retiring
    world.pyright(project).shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_all_reaches_a_retired_workspace_whose_holder_never_releases(
    tmp_path: Path, world: _World
) -> None:
    first = _project(tmp_path, "first")
    second = _project(tmp_path, "second")
    registry = WorkspaceRegistry(max_workspaces=1)
    await registry.get_backends(_source(first))  # evicted while leased, never released
    await registry.get_backends(_source(second))
    world.pyright(first).shutdown.assert_not_awaited()

    await registry.shutdown_all()

    world.pyright(first).shutdown.assert_awaited_once()
    world.pyright(second).shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_all_waits_for_a_deferred_shutdown_already_running(tmp_path: Path, world: _World) -> None:
    first = _project(tmp_path, "first")
    second = _project(tmp_path, "second")
    registry = WorkspaceRegistry(max_workspaces=1)
    held = await registry.get_backends(_source(first))
    registry.release(await registry.get_backends(_source(second)))
    entered, release = _gate_shutdown(world.pyright(first))
    registry.release(held)
    await entered.wait()

    teardown = asyncio.ensure_future(registry.shutdown_all())
    for _ in range(5):
        await asyncio.sleep(0)
    assert not teardown.done()

    release.set()
    await teardown
    assert not registry._retiring


@pytest.mark.asyncio
async def test_a_closed_registry_creates_no_workspace_for_a_request_queued_on_the_lock(
    tmp_path: Path, world: _World
) -> None:
    live = _project(tmp_path, "live")
    late = _project(tmp_path, "late")
    registry = WorkspaceRegistry()
    registry.release(await registry.get_backends(_source(live)))
    entered, release = _gate_shutdown(world.pyright(live))

    teardown = asyncio.ensure_future(registry.shutdown_all())
    await entered.wait()
    queued = asyncio.ensure_future(registry.get_backends(_source(late)))
    await asyncio.sleep(0)
    release.set()
    await teardown

    with pytest.raises(WorkspaceResolutionError, match="shut down"):
        await queued
    assert [root for root, _mock in world.pyrights] == [live]
    assert registry.active_backends() == []


@pytest.mark.asyncio
async def test_a_failed_deferred_shutdown_is_logged_not_left_unretrieved(
    tmp_path: Path, world: _World, caplog: pytest.LogCaptureFixture
) -> None:
    first = _project(tmp_path, "first")
    second = _project(tmp_path, "second")
    registry = WorkspaceRegistry(max_workspaces=1)
    held = await registry.get_backends(_source(first))
    await registry.get_backends(_source(second))
    world.pyright(first).shutdown.side_effect = _CleanupFailure()

    with caplog.at_level(logging.WARNING, logger="python_refactor_mcp.workspace_registry"):
        registry.release(held)
        await asyncio.gather(*registry._retiring, return_exceptions=True)
        await asyncio.sleep(0)

    assert any("Deferred workspace shutdown failed" in record.getMessage() for record in caplog.records)
    assert not registry._retiring


# -- The tool boundary holds the lease for the whole call ---------------------


def _boundary_ctx(registry: WorkspaceRegistry) -> SimpleNamespace:
    multi = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=multi, session=MagicMock()))


def _leases(registry: WorkspaceRegistry) -> list[int]:
    return [backends.leases for backends in registry.active_backends()]


async def _live_registry(project: Path) -> WorkspaceRegistry:
    registry = WorkspaceRegistry()
    registry.release(await registry.get_backends(_source(project)))
    return registry


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (None, None),
        (ToolInputError("bad input"), Exception),
        (PyrightError("backend down"), Exception),
        (RuntimeError("tool defect"), RuntimeError),
    ],
)
async def test_the_boundary_holds_the_lease_during_the_call_and_releases_it_after(
    tmp_path: Path, world: _World, failure: Exception | None, expected: type[Exception] | None
) -> None:
    project = _project(tmp_path, "project")
    registry = await _live_registry(project)
    seen: list[list[int]] = []

    async def tool(ctx: Any, file_path: str) -> str:
        _ = (ctx, file_path)
        seen.append(_leases(registry))
        if failure is not None:
            raise failure
        return "ok"

    wrapped = tool_error_boundary(tool)
    if expected is None:
        assert await wrapped(_boundary_ctx(registry), file_path=_source(project)) == "ok"
    else:
        with pytest.raises(expected):
            await wrapped(_boundary_ctx(registry), file_path=_source(project))

    assert seen == [[1]]
    assert _leases(registry) == [0]


@pytest.mark.asyncio
async def test_the_boundary_releases_the_lease_when_the_call_is_cancelled(tmp_path: Path, world: _World) -> None:
    project = _project(tmp_path, "project")
    registry = await _live_registry(project)
    started = asyncio.Event()

    async def tool(ctx: Any, file_path: str) -> None:
        _ = (ctx, file_path)
        started.set()
        await asyncio.Event().wait()

    task = asyncio.ensure_future(tool_error_boundary(tool)(_boundary_ctx(registry), file_path=_source(project)))
    await started.wait()
    assert _leases(registry) == [1]

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert _leases(registry) == [0]


@pytest.mark.asyncio
async def test_the_boundary_releases_the_lease_when_the_coroutine_is_closed(tmp_path: Path, world: _World) -> None:
    project = _project(tmp_path, "project")
    registry = await _live_registry(project)
    parked = asyncio.get_running_loop().create_future()

    async def tool(ctx: Any, file_path: str) -> None:
        _ = (ctx, file_path)
        await parked

    coro = cast(
        "Coroutine[Any, Any, None]",
        tool_error_boundary(tool)(_boundary_ctx(registry), file_path=_source(project)),
    )
    coro.send(None)  # runs to the parked await
    assert _leases(registry) == [1]

    coro.close()  # raises GeneratorExit at the await

    assert _leases(registry) == [0]
    parked.cancel()


@pytest.mark.asyncio
async def test_the_boundary_releases_the_lease_even_when_resetting_the_context_var_raises(
    tmp_path: Path, world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, "project")
    registry = await _live_registry(project)

    class _FailingReset:
        def set(self, value: object) -> object:
            _ = value
            return object()

        def reset(self, token: object) -> None:
            _ = token
            raise LookupError("reset failed")

    monkeypatch.setattr(tool_runtime, "_current_backends", _FailingReset())

    async def tool(ctx: Any, file_path: str) -> str:
        _ = (ctx, file_path)
        return "ok"

    with pytest.raises(LookupError, match="reset failed"):
        await tool_error_boundary(tool)(_boundary_ctx(registry), file_path=_source(project))

    assert _leases(registry) == [0]


@pytest.mark.asyncio
async def test_a_tool_on_an_evicted_workspace_keeps_it_alive_until_the_call_ends(
    tmp_path: Path, world: _World
) -> None:
    first = _project(tmp_path, "first")
    second = _project(tmp_path, "second")
    registry = WorkspaceRegistry(max_workspaces=1)
    inside = asyncio.Event()
    finish = asyncio.Event()

    async def tool(ctx: Any, file_path: str) -> None:
        _ = (ctx, file_path)
        inside.set()
        await finish.wait()

    call = asyncio.ensure_future(tool_error_boundary(tool)(_boundary_ctx(registry), file_path=_source(first)))
    await inside.wait()
    await registry.get_backends(_source(second))  # evicts `first` while the tool still runs

    world.pyright(first).shutdown.assert_not_awaited()
    finish.set()
    await call
    await _settle(registry)

    world.pyright(first).shutdown.assert_awaited_once()


def test_backends_are_identity_hashable() -> None:
    config = MagicMock()
    one = WorkspaceBackends(config=config, pyright=MagicMock(), jedi=MagicMock(), rope=MagicMock())
    two = WorkspaceBackends(config=config, pyright=MagicMock(), jedi=MagicMock(), rope=MagicMock())

    assert len({one, two}) == 2


# -- A worker thread keeps the lease after its caller is gone -----------------


async def _until(predicate: Callable[[], bool]) -> None:
    """Yield to the loop until *predicate* holds; a wall-clock guard turns a hang into a failure."""
    deadline = time.monotonic() + 10
    while not predicate():
        assert time.monotonic() < deadline, "condition never held"
        await asyncio.sleep(0)


async def _drain() -> None:
    for _ in range(10):
        await asyncio.sleep(0)


class _BlockedWorker:
    """A tool whose backend work blocks on a gate; the gate is always opened in a finally."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.gate = threading.Event()
        self.started = threading.Event()
        self.timeout = timeout

    def work(self) -> int:
        self.started.set()
        self.gate.wait(10)
        return 1

    async def tool(self, ctx: Any, file_path: str) -> int:
        _ = (ctx, file_path)
        return await run_in_thread(
            self.work, timeout=self.timeout, error_cls=RopeError, op_name="rope.blocked", logger=None
        )


@pytest.mark.asyncio
async def test_a_cancelled_handler_keeps_a_retired_workspace_open_until_the_worker_returns(
    tmp_path: Path, world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, "project")
    registry = await _live_registry(project)
    releases: list[WorkspaceBackends] = []
    original_release = registry.release
    monkeypatch.setattr(registry, "release", lambda b: (releases.append(b), original_release(b))[1])
    worker = _BlockedWorker()
    backends = registry.active_backends()[0]
    try:
        call = asyncio.ensure_future(
            tool_error_boundary(worker.tool)(_boundary_ctx(registry), file_path=_source(project))
        )
        await _until(worker.started.is_set)
        await registry.set_roots([])  # retires the leased workspace
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call
        await _drain()
        await asyncio.gather(*registry._retiring)

        world.pyright(project).shutdown.assert_not_awaited()
        assert backends.is_initialized is True
        assert backends.leases == 1  # only the worker's lease remains
    finally:
        worker.gate.set()

    await _until(lambda: backends.leases == 0)
    await _settle(registry)

    world.pyright(project).shutdown.assert_awaited_once()
    assert backends.is_initialized is False
    assert len(releases) == 2  # the request's release, then exactly one for the worker


@pytest.mark.asyncio
async def test_a_timed_out_worker_keeps_a_retired_workspace_open_until_it_returns(
    tmp_path: Path, world: _World
) -> None:
    project = _project(tmp_path, "project")
    registry = await _live_registry(project)
    worker = _BlockedWorker(timeout=0.05)
    backends = registry.active_backends()[0]
    try:
        call = asyncio.ensure_future(
            tool_error_boundary(worker.tool)(_boundary_ctx(registry), file_path=_source(project))
        )
        await _until(worker.started.is_set)
        await registry.set_roots([])
        with pytest.raises(ToolError):
            await call
        await _drain()
        await asyncio.gather(*registry._retiring)

        world.pyright(project).shutdown.assert_not_awaited()
        assert backends.leases == 1
    finally:
        worker.gate.set()

    await _until(lambda: backends.leases == 0)
    await _settle(registry)

    world.pyright(project).shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_tool_under_the_boundary_borrows_a_lease_for_its_worker(tmp_path: Path, world: _World) -> None:
    project = _project(tmp_path, "project")
    registry = await _live_registry(project)
    seen: list[int] = []

    async def tool(ctx: Any, file_path: str) -> None:
        _ = (ctx, file_path)
        backends = get_current_backends()
        await run_in_thread(
            lambda: seen.append(backends.leases), timeout=5.0, error_cls=RopeError, op_name="rope.probe", logger=None
        )

    await tool_error_boundary(tool)(_boundary_ctx(registry), file_path=_source(project))
    await _until(lambda: _leases(registry) == [0])

    assert seen == [2]  # the request lease plus the worker's


@pytest.mark.asyncio
async def test_shutdown_all_does_not_wait_for_a_running_worker(tmp_path: Path, world: _World) -> None:
    """Guard: server teardown never hangs on a worker thread (ADR 0010, ADR 0013)."""
    project = _project(tmp_path, "project")
    registry = await _live_registry(project)
    worker = _BlockedWorker()
    try:
        call = asyncio.ensure_future(
            tool_error_boundary(worker.tool)(_boundary_ctx(registry), file_path=_source(project))
        )
        await _until(worker.started.is_set)

        await asyncio.wait_for(registry.shutdown_all(), timeout=5)

        world.pyright(project).shutdown.assert_awaited_once()
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call
    finally:
        worker.gate.set()
    await _drain()
    assert not registry._retiring  # the late worker release schedules nothing


@pytest.mark.asyncio
async def test_the_boundary_releases_the_lease_even_when_resetting_the_worker_scope_raises(
    tmp_path: Path, world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, "project")
    registry = await _live_registry(project)

    class _FailingReset:
        def set(self, value: object) -> object:
            _ = value
            return object()

        def reset(self, token: object) -> None:
            _ = token
            raise LookupError("reset failed")

    monkeypatch.setattr(tool_runtime, "_worker_lease_scope", _FailingReset())

    async def tool(ctx: Any, file_path: str) -> str:
        _ = (ctx, file_path)
        return "ok"

    with pytest.raises(LookupError, match="reset failed"):
        await tool_error_boundary(tool)(_boundary_ctx(registry), file_path=_source(project))

    assert _leases(registry) == [0]
