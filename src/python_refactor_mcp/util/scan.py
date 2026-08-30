"""Shared, payload-safe Python source scanning primitives."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from python_refactor_mcp.models import ScanFailure


@dataclass(frozen=True)
class ParsedPythonFile:
    """A successfully decoded and parsed Python source file."""

    path: Path
    source: str
    tree: ast.Module


def parse_python_file(
    file_path: str | Path,
    *,
    phase: str = "read_or_parse",
) -> tuple[ParsedPythonFile | None, ScanFailure | None]:
    """Parse one file or return a redacted failure suitable for caller output."""
    path = Path(file_path).resolve()
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        return (
            None,
            ScanFailure(
                file_path=str(path),
                phase=phase,
                error_type=type(exc).__name__,
            ),
        )
    return ParsedPythonFile(path=path, source=source, tree=tree), None


__all__ = ["ParsedPythonFile", "parse_python_file"]
