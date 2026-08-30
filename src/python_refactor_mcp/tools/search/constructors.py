"""Find constructor call sites for a class."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    ConstructorSearchResult,
    ConstructorSite,
    Location,
    Position,
    Range,
    ScanFailure,
)
from python_refactor_mcp.util.scan import ParsedPythonFile, parse_python_file

from ._helpers import (
    PyrightSearchBackend,
    apply_limit_items,
    name_position,
    python_files,
    range_sort_key,
)


def _extract_call_arguments(call_node: ast.Call) -> list[str]:
    """Extract call-site arguments in source-like form."""
    arguments: list[str] = []
    for argument in call_node.args:
        arguments.append(ast.unparse(argument))
    for keyword in call_node.keywords:
        if keyword.arg is None:
            arguments.append(f"**{ast.unparse(keyword.value)}")
            continue
        arguments.append(f"{keyword.arg}={ast.unparse(keyword.value)}")
    return arguments


def _parse_files(
    paths: Iterable[Path],
    scan_failures: dict[str, ScanFailure],
) -> dict[str, ParsedPythonFile]:
    """Parse unique paths once and collect redacted failures by resolved path."""
    parsed_files: dict[str, ParsedPythonFile] = {}
    for path in paths:
        parsed, failure = parse_python_file(path)
        resolved = str(path.resolve())
        if parsed is None:
            if failure is not None:
                scan_failures[resolved] = failure
            continue
        parsed_files[str(parsed.path)] = parsed
    return parsed_files


def _class_definition_sites(
    class_name: str,
    parsed_files: Iterable[ParsedPythonFile],
) -> list[tuple[Path, int, int]]:
    """Find class definition sites by name across files."""
    matches: list[tuple[Path, int, int]] = []
    for parsed in parsed_files:
        lines = parsed.source.splitlines()
        for node in ast.walk(parsed.tree):
            if not isinstance(node, ast.ClassDef) or node.name != class_name:
                continue
            line_index = node.lineno - 1
            if line_index < 0 or line_index >= len(lines):
                continue
            char_index = name_position(lines[line_index], node.col_offset, node.name)
            matches.append((parsed.path, line_index, char_index))
    return matches


def _is_constructor_call_node(node: ast.AST, class_name: str) -> bool:
    """Return whether a call node invokes the target class name."""
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id == class_name
    if isinstance(node.func, ast.Attribute):
        return node.func.attr == class_name
    return False


def _call_range(call_node: ast.Call) -> Range | None:
    """Convert a call node into model range coordinates."""
    end_line = getattr(call_node, "end_lineno", None)
    end_column = getattr(call_node, "end_col_offset", None)
    if end_line is None or end_column is None:
        return None
    return Range(
        start=Position(line=call_node.lineno - 1, character=call_node.col_offset),
        end=Position(line=end_line - 1, character=end_column),
    )


async def find_constructors(
    pyright: PyrightSearchBackend,
    config: ServerConfig,
    class_name: str,
    file_path: str | None = None,
    limit: int | None = None,
) -> ConstructorSearchResult:
    """Find constructor call sites for a class across workspace files."""
    candidate_files = [Path(file_path).resolve()] if file_path is not None else python_files(config.workspace_root)
    scan_failures: dict[str, ScanFailure] = {}
    parsed_files = _parse_files(candidate_files, scan_failures)

    class_sites = _class_definition_sites(class_name, parsed_files.values())
    if not class_sites:
        return ConstructorSearchResult(
            items=[],
            total_count=0,
            files_scanned=len(parsed_files),
            scan_failures=list(scan_failures.values()),
        )

    references: list[Location] = []
    for class_file, class_line, class_char in class_sites:
        try:
            class_references = await pyright.get_references(
                str(class_file),
                class_line,
                class_char,
                True,
            )
        except Exception as exc:
            scan_failures[f"references:{class_file}:{class_line}:{class_char}"] = ScanFailure(
                file_path=str(class_file),
                phase="references",
                error_type=type(exc).__name__,
                subject=class_name,
            )
        else:
            references.extend(class_references)

    by_path: dict[str, list[Location]] = {}
    for reference in references:
        reference_path = getattr(reference, "file_path", None)
        if not isinstance(reference_path, str):
            continue
        by_path.setdefault(reference_path, []).append(reference)

    results: dict[tuple[str, int, int, int, int], ConstructorSite] = {}
    for referenced_path, file_references in by_path.items():
        resolved = str(Path(referenced_path).resolve())
        parsed = parsed_files.get(resolved)
        if parsed is None:
            parsed_candidates = _parse_files([Path(referenced_path)], scan_failures)
            parsed_files.update(parsed_candidates)
            parsed = parsed_candidates.get(resolved)
        if parsed is None:
            continue

        calls: list[ast.Call] = []
        for node in ast.walk(parsed.tree):
            if isinstance(node, ast.Call) and _is_constructor_call_node(node, class_name):
                calls.append(node)

        for reference in file_references:
            reference_range = getattr(reference, "range", None)
            start = getattr(reference_range, "start", None)
            ref_line = getattr(start, "line", None)
            ref_char = getattr(start, "character", None)
            if not isinstance(ref_line, int) or not isinstance(ref_char, int):
                continue

            for call in calls:
                call_range = _call_range(call)
                if call_range is None:
                    continue
                if call_range.start.line != ref_line:
                    continue
                if not (call_range.start.character <= ref_char < call_range.end.character):
                    continue

                site = ConstructorSite(
                    class_name=class_name,
                    file_path=str(parsed.path),
                    range=call_range,
                    arguments=_extract_call_arguments(call),
                )
                key = (
                    site.file_path,
                    site.range.start.line,
                    site.range.start.character,
                    site.range.end.line,
                    site.range.end.character,
                )
                results[key] = site

    # AST fallback: if Pyright references yielded no constructor matches,
    # scan all candidate files for direct constructor calls by name.
    if not results:
        candidate_paths = {str(path.resolve()) for path in candidate_files}
        for parsed in parsed_files.values():
            if str(parsed.path) not in candidate_paths:
                continue
            for node in ast.walk(parsed.tree):
                if isinstance(node, ast.Call) and _is_constructor_call_node(node, class_name):
                    call_range = _call_range(node)
                    if call_range is None:
                        continue
                    site = ConstructorSite(
                        class_name=class_name,
                        file_path=str(parsed.path),
                        range=call_range,
                        arguments=_extract_call_arguments(node),
                    )
                    key = (site.file_path, site.range.start.line, site.range.start.character,
                           site.range.end.line, site.range.end.character)
                    results[key] = site

    sorted_items = sorted(results.values(), key=lambda item: (item.file_path, *range_sort_key(item.range)))
    items = apply_limit_items(sorted_items, limit)
    return ConstructorSearchResult(
        items=items,
        total_count=len(sorted_items),
        truncated=len(items) < len(sorted_items),
        files_scanned=len(parsed_files),
        scan_failures=list(scan_failures.values()),
    )
