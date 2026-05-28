"""Shared async-to-thread helper for backend operations.

Both :class:`~python_refactor_mcp.backends.rope_backend.RopeBackend` and
:class:`~python_refactor_mcp.backends.jedi_backend.JediBackend` run their
synchronous work inside a worker thread under a timeout and re-raise any
failure as a backend-specific :class:`~python_refactor_mcp.errors.BackendError`
subclass. ``run_in_thread`` owns that shared shell so individual methods only
supply the work closure, timeout, error class, and operation name.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.util.timing import timed


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
    original exception chained via ``__cause__``.
    """
    try:
        if logger is not None:
            async with timed(logger, op_name):
                return await asyncio.wait_for(asyncio.to_thread(fn), timeout=timeout)
        return await asyncio.wait_for(asyncio.to_thread(fn), timeout=timeout)
    except Exception as exc:
        raise error_cls(f"{op_name} failed: {exc}") from exc
