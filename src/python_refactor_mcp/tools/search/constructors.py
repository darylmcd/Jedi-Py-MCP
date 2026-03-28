"""Find constructor call sites for a class."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    ConstructorSite,
    Location,
    Position,
    Range,
)

from ._helpers import (
    _apply_limit,
    _name_position,
    _PyrightSearchBackend,
    _python_files,
    _range_sort_key,
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


def _class_definition_sites(class_name: str, paths: Iterable[Path]) -> list[tuple[Path, int, int]]:
    """Find class definition sites by name across files."""
    matches: list[tuple[Path, int, int]] = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        try:
            module = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(module):
            if not isinstance(node, ast.ClassDef) or node.name != class_name:
                continue
            line_index = node.lineno - 1
            if line_index < 0 or line_index >= len(lines):
                continue
            char_index = _name_position(lines[line_index], node.col_offset, node.name)
            matches.append((path, line_index, char_index))
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
    pyright: _PyrightSearchBackend,
    config: ServerConfig,
    class_name: str,
    file_path: str | None = None,
    limit: int | None = None,
) -> list[ConstructorSite]:
    """Find constructor call sites for a class across workspace files."""
    candidate_files = [Path(file_path).resolve()] if file_path is not None else _python_files(config.workspace_root)

    class_sites = _class_definition_sites(class_name, candidate_files)
    if not class_sites:
        return []

    references: list[Location] = []
    for class_file, class_line, class_char in class_sites:
        class_references = await pyright.get_references(
            str(class_file),
            class_line,
            class_char,
            True,
        )
        references.extend(class_references)

    by_path: dict[str, list[Location]] = {}
    for reference in references:
        reference_path = getattr(reference, "file_path", None)
        if not isinstance(reference_path, str):
            continue
        by_path.setdefault(reference_path, []).append(reference)

    results: dict[tuple[str, int, int, int, int], ConstructorSite] = {}
    for referenced_path, file_references in by_path.items():
        path = Path(referenced_path)
        if not path.exists():
            continue

        source = path.read_text(encoding="utf-8")
        try:
            module = ast.parse(source)
        except SyntaxError:
            continue

        calls: list[ast.Call] = []
        for node in ast.walk(module):
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
                    file_path=str(path.resolve()),
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

    sorted_items = sorted(results.values(), key=lambda item: (item.file_path, *_range_sort_key(item.range)))
    return _apply_limit(sorted_items, limit)
