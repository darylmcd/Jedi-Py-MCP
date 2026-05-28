"""Unit tests for the shared ``run_in_thread`` backend helper."""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

from python_refactor_mcp.backends._threading import run_in_thread
from python_refactor_mcp.errors import BackendError, JediError, RopeError

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
