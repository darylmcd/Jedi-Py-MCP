"""Async subprocess lifecycle management for LSP server processes."""

from __future__ import annotations

import asyncio
import logging

from python_refactor_mcp.errors import PyrightError

_LOGGER = logging.getLogger(__name__)


class SubprocessManager:
    """Manages the lifecycle of an async subprocess (start, shutdown, cleanup)."""

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None

    @property
    def process(self) -> asyncio.subprocess.Process | None:
        return self._process

    def is_alive(self) -> bool:
        """Return True if the subprocess is running."""
        return self._process is not None and self._process.returncode is None

    def require_process(self) -> asyncio.subprocess.Process:
        """Return the running subprocess or raise a backend error."""
        if self._process is None:
            raise PyrightError("LSP subprocess has not been started.")
        return self._process

    async def start(self, command: list[str]) -> asyncio.subprocess.Process:
        """Start a subprocess with stdio pipes."""
        if self._process is not None:
            raise PyrightError("LSP subprocess is already running.")
        if not command:
            raise PyrightError("LSP command cannot be empty.")

        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if self._process.stdout is None or self._process.stdin is None or self._process.stderr is None:
            raise PyrightError("Failed to acquire stdio pipes for LSP subprocess.")

        return self._process

    async def shutdown(self) -> None:
        """Terminate the subprocess gracefully, then forcefully if needed."""
        process = self._process
        if process is None:
            return

        if process.stdin is not None:
            process.stdin.close()

        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except TimeoutError:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()

        self._process = None

    @staticmethod
    async def cancel_task(task: asyncio.Task[None] | None) -> None:
        """Cancel and await a background task if it exists."""
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return
