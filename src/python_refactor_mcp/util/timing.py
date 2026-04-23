"""Timing context manager for structured backend operation logging."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager


@asynccontextmanager
async def timed(logger: logging.Logger, operation: str) -> AsyncGenerator[None]:
    """Log start and elapsed time for an async operation at DEBUG level.

    Usage::

        async with timed(_LOGGER, "pyright.get_diagnostics"):
            result = await pyright.get_diagnostics(file_path)
    """
    start = time.perf_counter()
    logger.debug("%s: started", operation)
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug("%s: completed in %.1fms", operation, elapsed_ms)
