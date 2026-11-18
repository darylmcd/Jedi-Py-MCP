"""Shared async-to-thread helper for backend operations.

Both :class:`~python_refactor_mcp.backends.rope_backend.RopeBackend` and
:class:`~python_refactor_mcp.backends.jedi_backend.JediBackend` run their
synchronous work inside a worker thread under a timeout. ``run_in_thread`` owns
that shared shell so individual methods only supply the work closure, timeout,
error class, and operation name.

Failures: an exception raised by the work is re-raised as the backend-specific
:class:`~python_refactor_mcp.errors.BackendError` subclass ``error_cls``, with one
exception: :class:`~python_refactor_mcp.errors.ToolInputError` reports the caller's
own input, so it propagates unchanged.

Worker lease: a thread cannot be stopped, so a caller that is cancelled or times out
leaves its worker running. While a :data:`worker_lease_scope` is set (the tool
boundary sets it), the worker holds its own lease on the workspace from dispatch until
its task finishes, so a retired workspace is not shut down under it (ADR 0013). The
lease is released when the worker task completes, which is when the thread returns;
the one exception is event-loop teardown, which cancels the task while its thread may
still run.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import threading
from collections.abc import Callable

from python_refactor_mcp.errors import BackendError, ToolInputError
from python_refactor_mcp.util.timing import timed

_LOGGER = logging.getLogger(__name__)

# Borrows one extra workspace lease and returns the callable that gives it back. Set
# by ``tool_error_boundary`` for the length of a tool call; unset for direct backend
# callers, which have no workspace registry to protect.
type WorkerLeaseScope = Callable[[], Callable[[], None]]
worker_lease_scope: contextvars.ContextVar[WorkerLeaseScope | None] = contextvars.ContextVar(
    "worker_lease_scope", default=None
)


class _CallerGone(Exception):
    """A queued worker found its caller gone before it started; nobody receives it."""


def _finish_worker[T](worker: asyncio.Future[T], release: Callable[[], None] | None) -> None:
    """Retire a finished worker task: retrieve its outcome, then give its lease back once."""
    if not worker.cancelled():
        worker.exception()  # an abandoned worker's failure has no caller left to receive it
    if release is not None:
        try:
            release()
        except Exception:
            _LOGGER.warning("Releasing the worker lease failed", exc_info=True)


async def run_in_thread[T](
    fn: Callable[[], T],
    *,
    timeout: float,
    error_cls: type[BackendError],
    op_name: str,
    logger: logging.Logger | None = None,
) -> T:
    """Run ``fn`` in a worker thread under ``timeout`` and re-raise failures.

    The synchronous callable ``fn`` is dispatched via ``asyncio.to_thread`` and
    awaited under ``asyncio.wait_for(..., timeout=timeout)``. When ``logger`` is
    provided the await is wrapped in :func:`~python_refactor_mcp.util.timing.timed`
    so start/elapsed lines are emitted at DEBUG level; when ``logger`` is ``None``
    the timing scope is skipped entirely.

    Any exception raised by the work (including ``asyncio.TimeoutError``, which
    is a subclass of ``Exception``) is re-raised as ``error_cls`` with the
    original exception chained via ``__cause__``. The one exception is
    :class:`~python_refactor_mcp.errors.ToolInputError`: it reports the
    caller's own input, not a backend failure, so it propagates unchanged and
    keeps its caller-facing message.

    The worker task is shielded: cancelling the caller or timing out abandons the
    wait, never the thread. A worker still queued when its caller leaves is skipped
    rather than run. See the module docstring for the worker lease.
    """
    scope = worker_lease_scope.get()
    release = scope() if scope is not None else None
    abandoned = threading.Event()

    def _guarded() -> T:
        # Only a worker that has not started is skipped; one already running finishes.
        if abandoned.is_set():
            raise _CallerGone(op_name)
        return fn()

    try:
        worker = asyncio.ensure_future(asyncio.to_thread(_guarded))
    except BaseException:
        if release is not None:
            release()
        raise
    worker.add_done_callback(lambda done: _finish_worker(done, release))
    try:
        if logger is not None:
            async with timed(logger, op_name):
                return await asyncio.wait_for(asyncio.shield(worker), timeout=timeout)
        return await asyncio.wait_for(asyncio.shield(worker), timeout=timeout)
    except ToolInputError:
        raise
    except Exception as exc:
        abandoned.set()
        raise error_cls(f"{op_name} failed: {exc}") from exc
    except BaseException:
        abandoned.set()
        raise
