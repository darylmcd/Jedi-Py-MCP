"""Audit the public export surface for symbols with zero cross-file references.

``unused_symbol_sweep`` is the export-surface complement to
:func:`python_refactor_mcp.tools.search.dead_code.dead_code_detection`. Where
``dead_code_detection`` scans *undecorated* module-level symbols, this sweep
covers the full public API surface — ``__all__``-listed names when an
``__all__`` is present, otherwise every non-underscore module-level name —
*regardless of decoration*, and flags any with no inbound references from
another file. Symbols registered through an external decorator (anything whose
decorator name contains ``mcp`` or ``tool``, e.g. ``@mcp.tool``) are skipped to
avoid false positives, mirroring the rationale behind ``dead_code_detection``'s
blanket decorator skip.

The sweep may be slow on large codebases: it issues one ``get_references`` call
per exported symbol. ``limit`` bounds the response size but not the work done.
"""

from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import DeadCodeItem, PaginatedDeadCode, Position, Range, ScanFailure

from ._helpers import PyrightSearchBackend, name_position, python_files


def _is_test_file(path: Path) -> bool:
    """Return True if the file looks like a test file."""
    name = path.name
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def _resolve_targets(
    file_path: str | None,
    file_paths: list[str] | None,
    root_path: str | None,
    config: ServerConfig,
    exclude_test_files: bool,
) -> list[Path]:
    """Determine which files to scan for unused exports."""
    if file_path is not None and file_paths is not None:
        raise ValueError("file_path and file_paths are mutually exclusive")
    effective_root = Path(root_path).resolve() if root_path else config.workspace_root
    if file_paths is not None:
        targets = [Path(p).resolve() for p in file_paths]
    elif file_path is not None:
        targets = [Path(file_path).resolve()]
    else:
        targets = python_files(effective_root)
    if exclude_test_files:
        targets = [p for p in targets if not _is_test_file(p)]
    return targets


def _confidence(name: str) -> str:
    """Score confidence that an unreferenced export is genuinely unused."""
    lower = name.lower()
    if lower in {"logger", "_logger", "log", "_log"}:
        return "low"
    if name.startswith("test_") or name.startswith("Test"):
        return "low"
    if name.startswith("__") and name.endswith("__"):
        return "low"
    return "medium"


def _decorator_skips_symbol(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> bool:
    """Return True if a decorator marks the symbol as externally registered.

    Decorators whose dotted name contains ``mcp`` or ``tool`` (e.g. ``@mcp.tool``)
    register the symbol with a framework, so a zero-reference result is expected
    and not evidence of dead code.
    """
    for decorator in node.decorator_list:
        target: ast.expr = decorator.func if isinstance(decorator, ast.Call) else decorator
        parts: list[str] = []
        while isinstance(target, ast.Attribute):
            parts.append(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            parts.append(target.id)
        dotted = ".".join(reversed(parts)).lower()
        if "mcp" in dotted or "tool" in dotted:
            return True
    return False


def _module_exports(module: ast.Module) -> set[str] | None:
    """Return the names listed in a module-level ``__all__``, or None if absent."""
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            continue
        value = node.value
        if isinstance(value, (ast.List, ast.Tuple)):
            return {
                element.value
                for element in value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
    return None


def _iter_export_symbols(file_path: Path) -> list[tuple[str, str, Range]]:
    """Collect module-level symbols that form the file's public export surface.

    A symbol is in scope when it is listed in ``__all__`` (if the module defines
    one) or, absent ``__all__``, when its name does not start with an underscore.
    Symbols registered via an external decorator are excluded.
    """
    source = file_path.read_text(encoding="utf-8")
    lines = source.splitlines()
    try:
        module = ast.parse(source)
    except SyntaxError:
        return []

    exports = _module_exports(module)

    def in_surface(name: str) -> bool:
        if name == "__all__":
            return False
        if exports is not None:
            return name in exports
        return not name.startswith("_")

    symbols: list[tuple[str, str, Range]] = []
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if _decorator_skips_symbol(node) or not in_surface(node.name):
                continue
            line_index = node.lineno - 1
            if line_index < 0 or line_index >= len(lines):
                continue
            char_index = name_position(lines[line_index], node.col_offset, node.name)
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            symbols.append(
                (
                    node.name,
                    kind,
                    Range(
                        start=Position(line=line_index, character=char_index),
                        end=Position(line=line_index, character=char_index + len(node.name)),
                    ),
                )
            )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Name) or not in_surface(target.id):
                    continue
                symbols.append(
                    (
                        target.id,
                        "variable",
                        Range(
                            start=Position(line=target.lineno - 1, character=target.col_offset),
                            end=Position(
                                line=target.lineno - 1,
                                character=target.col_offset + len(target.id),
                            ),
                        ),
                    )
                )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target
            if not in_surface(target.id):
                continue
            symbols.append(
                (
                    target.id,
                    "variable",
                    Range(
                        start=Position(line=target.lineno - 1, character=target.col_offset),
                        end=Position(line=target.lineno - 1, character=target.col_offset + len(target.id)),
                    ),
                )
            )
    return symbols


async def _check_export_symbol(
    pyright: PyrightSearchBackend,
    sem: asyncio.Semaphore,
    path: Path,
    name: str,
    kind: str,
    symbol_range: Range,
) -> DeadCodeItem | None:
    """Return a dead-code item when an exported symbol has no cross-file references."""
    async with sem:
        references = await pyright.get_references(
            str(path),
            symbol_range.start.line,
            symbol_range.start.character,
            False,
        )
    resolved_path = str(path.resolve())
    for ref in references:
        ref_path = getattr(ref, "file_path", None)
        if isinstance(ref_path, str) and ref_path != resolved_path:
            return None
    return DeadCodeItem(
        name=name,
        kind=kind,
        file_path=resolved_path,
        range=symbol_range,
        reason="no external references",
        confidence=_confidence(name),
    )


async def unused_symbol_sweep(
    pyright: PyrightSearchBackend,
    config: ServerConfig,
    file_path: str | None = None,
    exclude_patterns: list[str] | None = None,
    root_path: str | None = None,
    exclude_test_files: bool = True,
    file_paths: list[str] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> PaginatedDeadCode:
    """Audit the public export surface for symbols with no cross-file references."""
    target_files = _resolve_targets(file_path, file_paths, root_path, config, exclude_test_files)
    compiled_excludes = [re.compile(pattern) for pattern in (exclude_patterns or [])]

    symbols_to_check: list[tuple[Path, str, str, Range]] = []
    for path in target_files:
        if not path.exists():
            continue
        for name, kind, symbol_range in _iter_export_symbols(path):
            if any(pattern.search(name) for pattern in compiled_excludes):
                continue
            symbols_to_check.append((path, name, kind, symbol_range))

    sem = asyncio.Semaphore(10)
    results = await asyncio.gather(
        *[_check_export_symbol(pyright, sem, p, n, k, r) for p, n, k, r in symbols_to_check],
        return_exceptions=True,
    )

    unused: dict[tuple[str, str, int, int], DeadCodeItem] = {}
    scan_failures: list[ScanFailure] = []
    for (path, name, _kind, _symbol_range), result in zip(
        symbols_to_check, results, strict=True
    ):
        if isinstance(result, DeadCodeItem):
            key = (result.file_path, result.name, result.range.start.line, result.range.start.character)
            unused[key] = result
        elif isinstance(result, BaseException):
            scan_failures.append(
                ScanFailure(
                    file_path=str(path.resolve()),
                    phase="references",
                    error_type=type(result).__name__,
                    subject=name,
                )
            )

    all_items = sorted(
        unused.values(),
        key=lambda item: (item.file_path, item.name, item.range.start.line, item.range.start.character),
    )
    total_count = len(all_items)
    items = all_items[offset:] if offset > 0 else all_items
    truncated = False
    if limit is not None and limit > 0 and len(items) > limit:
        items = items[:limit]
        truncated = True
    return PaginatedDeadCode(
        items=items,
        total_count=total_count,
        offset=offset,
        truncated=truncated,
        scan_failures=scan_failures,
    )
