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
    results: list[StaticError] = []
    for err in raw_errors:
        raw_line = err.get("line", 0)
        line_no = int(raw_line) if isinstance(raw_line, (int, str)) else 0
        results.append(StaticError(
            file_path=str(err.get("file_path", file_path)),
            line=line_no,
            message=str(err.get("message", "")),
        ))
    return results
