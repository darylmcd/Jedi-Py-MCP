"""Unit tests for the shared ``run_in_thread`` backend helper."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest

from python_refactor_mcp.backends import _threading
from python_refactor_mcp.backends._threading import run_in_thread
from python_refactor_mcp.errors import BackendError, JediError, RopeError, ToolInputError

_LOGGER = logging.getLogger("python_refactor_mcp.backends._threading_test")


@pytest.mark.asyncio
async def test_returns_work_result() -> None:
    """The helper returns the closure's value on the happy path."""

    def _work() -> int:
        return 42

    result = await run_in_thread(
        _work, timeout=5.0, error_cls=RopeError, op_name="rope.happy", logger=None,
    )

    assert result == 42


@pytest.mark.asyncio
async def test_generic_exception_reraised_as_error_cls() -> None:
    """A generic exception in the closure is re-raised as ``error_cls``."""

    def _work() -> int:
        raise ValueError("boom")

    with pytest.raises(RopeError) as exc_info:
        await run_in_thread(
            _work, timeout=5.0, error_cls=RopeError, op_name="rope.boom", logger=None,
        )

    assert "rope.boom failed" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, ValueError)
    assert str(exc_info.value.__cause__) == "boom"


@pytest.mark.asyncio
async def test_tool_input_error_propagates_unwrapped() -> None:
    """A caller-input error keeps its type and message instead of becoming ``error_cls``."""

    def _work() -> int:
        raise ToolInputError("index must be >= 0 (parameter: index)")

    with pytest.raises(ToolInputError) as exc_info:
        await run_in_thread(
            _work, timeout=5.0, error_cls=RopeError, op_name="rope.input", logger=None,
        )

    assert not isinstance(exc_info.value, BackendError)
    assert str(exc_info.value) == "index must be >= 0 (parameter: index)"


@pytest.mark.asyncio
async def test_jedi_error_class_is_honored() -> None:
    """The supplied ``error_cls`` selects the raised backend error type."""

    def _work() -> int:
        raise RuntimeError("nope")

    with pytest.raises(JediError) as exc_info:
        await run_in_thread(
            _work, timeout=5.0, error_cls=JediError, op_name="jedi.nope", logger=None,
        )

    assert "jedi.nope failed" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, RuntimeError)


@pytest.mark.asyncio
async def test_timeout_reraised_as_error_cls_not_raw_timeout() -> None:
    """A timed-out closure surfaces as ``error_cls`` with a TimeoutError cause."""

    def _work() -> int:
        time.sleep(1.0)
        return 1

    with pytest.raises(RopeError) as exc_info:
        await run_in_thread(
            _work, timeout=0.01, error_cls=RopeError, op_name="rope.slow", logger=None,
        )

    assert "rope.slow failed" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, asyncio.TimeoutError)
    # asyncio.TimeoutError must NOT escape unwrapped.
    assert isinstance(exc_info.value, BackendError)


@pytest.mark.asyncio
async def test_logger_none_skips_timed(caplog: pytest.LogCaptureFixture) -> None:
    """With ``logger=None`` no timing debug lines are emitted."""

    def _work() -> str:
        return "ok"

    with caplog.at_level(logging.DEBUG, logger="python_refactor_mcp.util.timing"):
        result = await run_in_thread(
            _work, timeout=5.0, error_cls=RopeError, op_name="rope.silent", logger=None,
        )

    assert result == "ok"
    timing_records = [r for r in caplog.records if "rope.silent" in r.getMessage()]
    assert timing_records == []


@pytest.mark.asyncio
async def test_logger_emits_start_and_completed(caplog: pytest.LogCaptureFixture) -> None:
    """With a logger the timed wrapper emits start and completed debug lines."""

    def _work() -> str:
        return "done"

    with caplog.at_level(logging.DEBUG):
        result = await run_in_thread(
            _work, timeout=5.0, error_cls=RopeError, op_name="rope.timed_op", logger=_LOGGER,
        )

    assert result == "done"
    messages = [r.getMessage() for r in caplog.records]
    assert any("rope.timed_op: started" in m for m in messages)
    assert any("rope.timed_op: completed" in m for m in messages)


@pytest.mark.asyncio
async def test_logger_emits_started_even_on_failure(caplog: pytest.LogCaptureFixture) -> None:
    """The timed wrapper still records start/completed when the closure raises."""

    def _work() -> str:
        raise ValueError("explode")

    with caplog.at_level(logging.DEBUG), pytest.raises(RopeError):
        await run_in_thread(
            _work, timeout=5.0, error_cls=RopeError, op_name="rope.fail_timed", logger=_LOGGER,
        )

    messages = [r.getMessage() for r in caplog.records]
    # ``timed`` logs "started" on entry and "completed" in its finally block.
    assert any("rope.fail_timed: started" in m for m in messages)
    assert any("rope.fail_timed: completed" in m for m in messages)


# -- Worker lease: a borrowed lease outlives an abandoned worker --------------


class _Scope:
    """A lease scope that counts borrows and releases."""

    def __init__(self) -> None:
        self.borrowed = 0
        self.released = 0

    def __call__(self) -> Callable[[], None]:
        self.borrowed += 1

        def release() -> None:
            self.released += 1

        return release


async def _until(predicate: Callable[[], bool]) -> None:
    """Yield to the loop until *predicate* holds; a wall-clock guard turns a hang into a failure."""
    deadline = time.monotonic() + 10
    while not predicate():
        assert time.monotonic() < deadline, "condition never held"
        await asyncio.sleep(0)


@pytest.fixture
def scope() -> Iterator[_Scope]:
    counting = _Scope()
    token = _threading.worker_lease_scope.set(counting)
    try:
        yield counting
    finally:
        _threading.worker_lease_scope.reset(token)


async def _run(work: Callable[[], object], *, timeout: float = 5.0) -> object:
    return await run_in_thread(work, timeout=timeout, error_cls=RopeError, op_name="rope.leased", logger=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "worker_error", "input_error"])
async def test_lease_is_borrowed_and_released_once_when_the_worker_finishes(scope: _Scope, outcome: str) -> None:
    def _work() -> int:
        if outcome == "worker_error":
            raise ValueError("boom")
        if outcome == "input_error":
            raise ToolInputError("bad (parameter: x)")
        return 1

    if outcome == "success":
        assert await _run(_work) == 1
    else:
        with pytest.raises((RopeError, ToolInputError)):
            await _run(_work)
    await _until(lambda: scope.released >= 1)
    for _ in range(5):
        await asyncio.sleep(0)

    assert (scope.borrowed, scope.released) == (1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("how", ["cancel", "timeout"])
async def test_lease_outlives_a_cancelled_or_timed_out_caller_until_the_worker_returns(
    scope: _Scope, how: str
) -> None:
    gate = threading.Event()
    started = threading.Event()

    def _work() -> int:
        started.set()
        gate.wait(10)
        return 1

    try:
        task = asyncio.ensure_future(_run(_work, timeout=0.05 if how == "timeout" else 5.0))
        await _until(started.is_set)
        if how == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(RopeError):
                await task
        for _ in range(10):
            await asyncio.sleep(0)

        assert (scope.borrowed, scope.released) == (1, 0)  # caller gone, worker still running
    finally:
        gate.set()
    await _until(lambda: scope.released >= 1)
    for _ in range(5):
        await asyncio.sleep(0)

    assert (scope.borrowed, scope.released) == (1, 1)


@pytest.mark.asyncio
async def test_a_worker_that_never_started_is_skipped_when_its_caller_leaves(scope: _Scope) -> None:
    executor = ThreadPoolExecutor(max_workers=1)
    asyncio.get_running_loop().set_default_executor(executor)
    gate = threading.Event()
    started = threading.Event()
    ran: list[str] = []

    def _first() -> None:
        started.set()
        gate.wait(10)

    def _second() -> None:
        ran.append("second")

    first = asyncio.ensure_future(_run(_first))
    try:
        await _until(started.is_set)
        second = asyncio.ensure_future(_run(_second))
        for _ in range(5):
            await asyncio.sleep(0)
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
    finally:
        gate.set()
    await first
    await _until(lambda: scope.released >= 2)
    executor.shutdown(wait=True)

    assert ran == []
    assert (scope.borrowed, scope.released) == (2, 2)


@pytest.mark.asyncio
async def test_without_a_scope_the_helper_borrows_nothing() -> None:
    """Guard: direct backend callers (no tool boundary) are unchanged."""
    assert _threading.worker_lease_scope.get() is None
    assert await _run(lambda: 7) == 7


@pytest.mark.asyncio
async def test_a_failing_release_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    def _bad_scope() -> Callable[[], None]:
        def release() -> None:
            raise RuntimeError("release defect")

        return release

    token = _threading.worker_lease_scope.set(_bad_scope)
    try:
        with caplog.at_level(logging.WARNING, logger="python_refactor_mcp.backends._threading"):
            assert await _run(lambda: 1) == 1
            await _until(lambda: any("worker lease failed" in r.getMessage() for r in caplog.records))
    finally:
        _threading.worker_lease_scope.reset(token)
