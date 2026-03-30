"""Test coverage mapping: source symbols to test references."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Protocol

from python_refactor_mcp.models import Location, TestCoverageEntry, TestCoverageMap

_LOGGER = logging.getLogger(__name__)


class _ReferencesBackend(Protocol):
    """Protocol for backends that can find references."""

    async def get_references(
        self, file_path: str, line: int, char: int, include_declaration: bool,
    ) -> list[Location]:
        ...


async def get_test_coverage_map(
    pyright: _ReferencesBackend,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
) -> TestCoverageMap:
    """Map source symbols to test file references."""
    paths: list[str] = []
    if file_paths:
        paths.extend(file_paths)
    if file_path:
        paths.append(file_path)

    entries: list[TestCoverageEntry] = []
    for path in paths:
        try:
            source = Path(path).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=path)
        except (OSError, SyntaxError):
            continue

        source_lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            name = node.name
            line = node.lineno - 1
            col = source_lines[line].find(name) if 0 <= line < len(source_lines) else 0
            if col < 0:
                col = 0

            try:
                refs = await pyright.get_references(path, line, max(col, 0), True)
            except Exception:
                _LOGGER.debug("reference lookup failed for %s:%s", path, name, exc_info=True)
                refs = []

            test_refs = sorted({
                ref.file_path for ref in refs
                if "test" in Path(ref.file_path).name.lower() or "tests" in str(ref.file_path).lower()
            })
            entries.append(TestCoverageEntry(
                symbol_name=name,
                file_path=path,
                line=line,
                test_references=test_refs,
                covered=len(test_refs) > 0,
            ))

    covered = sum(1 for e in entries if e.covered)
    total = len(entries)
    return TestCoverageMap(
        entries=entries,
        total_symbols=total,
        covered_count=covered,
        coverage_pct=round(covered / total * 100, 1) if total > 0 else 0.0,
    )
