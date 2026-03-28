"""Static error analysis using rope's finderrors module."""

from __future__ import annotations

from typing import Protocol

from python_refactor_mcp.models import StaticError


class _RopeErrorBackend(Protocol):
    async def find_errors(self, file_path: str) -> list[dict[str, object]]: ...


async def find_errors_static(
    rope: _RopeErrorBackend,
    file_path: str,
) -> list[StaticError]:
    """Run rope's static analysis for bad name/attribute accesses."""
    raw_errors = await rope.find_errors(file_path)
    return [
        StaticError(
            file_path=str(err.get("file_path", file_path)),
            line=int(err.get("line", 0)),
            message=str(err.get("message", "")),
        )
        for err in raw_errors
    ]
