"""Detect dead code candidates using diagnostics and reference counts."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    DeadCodeItem,
    Diagnostic,
    PaginatedDeadCode,
    Position,
    Range,
)

from ._helpers import (
    _DIAGNOSTIC_TAG_UNNECESSARY,
    _name_position,
    _PyrightSearchBackend,
    _python_files,
)


def _score_confidence(name: str, reason: str) -> str:
    """Score confidence of a dead code candidate using heuristics."""
    if reason == "unused diagnostic":
        return "high"
    lower = name.lower()
    if lower in {"logger", "_logger", "log", "_log"}:
        return "low"
    if name.startswith("test_") or name.startswith("Test"):
        return "low"
    if name.startswith("__") and name.endswith("__"):
        return "low"
    return "medium"


def _is_test_file(path: Path) -> bool:
    """Return True if the file looks like a test file."""
    name = path.name
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def _iter_module_level_symbols(file_path: Path) -> list[tuple[str, str, Range]]:
    """Collect module-level symbol declarations for dead code scans."""
    source = file_path.read_text(encoding="utf-8")
    lines = source.splitlines()
    try:
        module = ast.parse(source)
    except SyntaxError:
        return []

    symbols: list[tuple[str, str, Range]] = []
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            line_index = node.lineno - 1
            if line_index < 0 or line_index >= len(lines):
                continue
            char_index = _name_position(lines[line_index], node.col_offset, node.name)
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
                if not isinstance(target, ast.Name):
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


async def dead_code_detection(
    pyright: _PyrightSearchBackend,
    config: ServerConfig,
    file_path: str | None = None,
    exclude_patterns: list[str] | None = None,
    root_path: str | None = None,
    exclude_test_files: bool = True,
    file_paths: list[str] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> PaginatedDeadCode:
    """Detect dead code candidates using diagnostics and reference counts."""
    if file_path is not None and file_paths is not None:
        raise ValueError("file_path and file_paths are mutually exclusive")
    effective_root = Path(root_path).resolve() if root_path else config.workspace_root
    if file_paths is not None:
        target_files = [Path(p).resolve() for p in file_paths]
    elif file_path is not None:
        target_files = [Path(file_path).resolve()]
    else:
        target_files = _python_files(effective_root)
    if exclude_test_files:
        target_files = [p for p in target_files if not _is_test_file(p)]
    target_paths = {str(p.resolve()) for p in target_files}

    dead_items: dict[tuple[str, str, int, int], DeadCodeItem] = {}

    compiled_excludes = [re.compile(pattern) for pattern in (exclude_patterns or [])]

    # Collect diagnostics per target file to ensure scope matches the symbol scan.
    all_diagnostics: list[Diagnostic] = []
    for path in target_files:
        if not path.exists():
            continue
        file_diags = await pyright.get_diagnostics(str(path))
        all_diagnostics.extend(
            d for d in file_diags if d.file_path in target_paths
        )

    for diagnostic in all_diagnostics:
        lowered = diagnostic.message.lower()
        has_unnecessary_tag = _DIAGNOSTIC_TAG_UNNECESSARY in diagnostic.tags
        if not has_unnecessary_tag and "unused" not in lowered and "not accessed" not in lowered:
            continue

        quoted = re.findall(r"['\"]([^'\"]+)['\"]", diagnostic.message)
        name = quoted[0] if quoted else "unknown"
        reason = "unused diagnostic"
        item = DeadCodeItem(
            name=name,
            kind="import" if "import" in lowered else "symbol",
            file_path=diagnostic.file_path,
            range=diagnostic.range,
            reason=reason,
            confidence=_score_confidence(name, reason),
        )
        key = (item.file_path, item.name, item.range.start.line, item.range.start.character)
        dead_items[key] = item

    for path in target_files:
        if not path.exists():
            continue
        for name, kind, symbol_range in _iter_module_level_symbols(path):
            if any(pattern.search(name) for pattern in compiled_excludes):
                continue
            references = await pyright.get_references(
                str(path),
                symbol_range.start.line,
                symbol_range.start.character,
                False,
            )
            same_file_refs = []
            external_refs = []
            for ref in references:
                ref_path = getattr(ref, "file_path", None)
                if not isinstance(ref_path, str):
                    continue
                if ref_path == str(path.resolve()):
                    same_file_refs.append(ref)
                else:
                    external_refs.append(ref)
            if external_refs:
                continue
            # If there are same-file usages beyond just the definition, the symbol
            # is an internal helper and not truly dead.
            if len(same_file_refs) > 1:
                continue

            reason = "no references"
            item = DeadCodeItem(
                name=name,
                kind=kind,
                file_path=str(path.resolve()),
                range=symbol_range,
                reason=reason,
                confidence=_score_confidence(name, reason),
            )
            key = (item.file_path, item.name, item.range.start.line, item.range.start.character)
            dead_items[key] = item

    all_items = sorted(
        dead_items.values(),
        key=lambda item: (
            item.file_path,
            item.name,
            item.range.start.line,
            item.range.start.character,
        ),
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
    )
