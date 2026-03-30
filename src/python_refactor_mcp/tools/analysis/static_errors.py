"""Static error analysis using rope's finderrors module."""

from __future__ import annotations

from typing import Protocol

from python_refactor_mcp.models import StaticError


class _RopeErrorBackend(Protocol):
    async def find_errors(self, file_path: str) -> list[dict[str, object]]: ...


_FALSE_POSITIVE_PATTERNS = (
    # Rope flags dict/set/list built-in methods as "Unresolved attribute"
    # because it can't infer container types from complex expressions.
    "Unresolved attribute",
    # Loop variables and comprehension targets are flagged as "Defined later"
    # when rope's analysis visits usage before the for-loop header.
    "Defined later",
)


async def find_errors_static(
    rope: _RopeErrorBackend,
    file_path: str,
) -> list[StaticError]:
    """Run rope's static analysis for bad name/attribute accesses.

    Filters out known rope false-positive patterns (dict/set attribute access,
    loop variable "defined later" warnings) that are reliably caught by Pyright.
    """
    raw_errors = await rope.find_errors(file_path)
    results: list[StaticError] = []
    for err in raw_errors:
        message = str(err.get("message", ""))
        # Skip known false-positive patterns.
        if any(pattern in message for pattern in _FALSE_POSITIVE_PATTERNS):
            continue
        raw_line = err.get("line", 0)
        line_no = int(raw_line) if isinstance(raw_line, (int, str)) else 0
        results.append(StaticError(
            file_path=str(err.get("file_path", file_path)),
            line=line_no,
            message=message,
        ))
    return results
