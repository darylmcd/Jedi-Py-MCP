"""Test coverage mapping: source symbols to test references."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Protocol

from python_refactor_mcp.models import Location, ScanFailure, TestCoverageEntry, TestCoverageMap
from python_refactor_mcp.util.scan import parse_python_file


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
    scan_failures: list[ScanFailure] = []
    for path in paths:
        parsed, failure = parse_python_file(path)
        if parsed is None:
            if failure is not None:
                scan_failures.append(failure)
            continue

        source_lines = parsed.source.splitlines()
        for node in ast.walk(parsed.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            name = node.name
            line = node.lineno - 1
            col = source_lines[line].find(name) if 0 <= line < len(source_lines) else 0
            if col < 0:
                col = 0

            try:
                refs = await pyright.get_references(str(parsed.path), line, max(col, 0), True)
            except Exception as exc:
                scan_failures.append(
                    ScanFailure(
                        file_path=str(parsed.path),
                        phase="references",
                        error_type=type(exc).__name__,
                        subject=name,
                    )
                )
                continue

            test_refs = sorted({
                ref.file_path for ref in refs
                if "test" in Path(ref.file_path).name.lower() or "tests" in str(ref.file_path).lower()
            })
            entries.append(TestCoverageEntry(
                symbol_name=name,
                file_path=str(parsed.path),
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
        files_scanned=len(paths) - sum(1 for failure in scan_failures if failure.phase == "read_or_parse"),
        scan_failures=scan_failures,
    )
