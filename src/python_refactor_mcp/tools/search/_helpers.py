"""Shared helpers, protocols, and constants used across search submodules."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    Diagnostic,
    ImportSuggestion,
    Location,
    Position,
    Range,
    SymbolInfo,
)
from python_refactor_mcp.util.file_filter import python_files as _filtered_python_files

DIAGNOSTIC_TAG_UNNECESSARY = 1


@dataclass(frozen=True, slots=True)
class ModuleLevelSymbol:
    """One module-level declaration and the metadata needed by search scans."""

    name: str
    kind: str
    range: Range
    decorator_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModuleSymbolScan:
    """One parsed module's declarations and explicit export surface."""

    symbols: tuple[ModuleLevelSymbol, ...]
    explicit_exports: frozenset[str] | None


class PyrightSearchBackend(Protocol):
    """Protocol describing Pyright search methods used by this module."""

    async def get_references(
        self,
        file_path: str,
        line: int,
        char: int,
        include_declaration: bool,
    ) -> list[Location]:
        """Return references for a symbol position."""
        ...

    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]:
        """Return diagnostics for one file or the full workspace."""
        ...

    async def get_code_actions(
        self,
        file_path: str,
        range_value: Range,
        diagnostics: list[Diagnostic],
    ) -> list[dict[str, object]]:
        """Return code action candidates for a range."""
        ...

    async def workspace_symbol(self, query: str) -> list[SymbolInfo]:
        """Search workspace symbols by query string."""
        ...


class JediSearchBackend(Protocol):
    """Protocol describing Jedi search methods used by this module."""

    async def search_names(self, symbol: str) -> list[ImportSuggestion]:
        """Search names and convert them into import suggestions."""
        ...

    async def search_symbols(self, query: str) -> list[SymbolInfo]:
        """Search project symbols by query string."""
        ...


def python_files(root: Path) -> list[Path]:
    """Return Python files below a root path in stable order, excluding common non-project dirs."""
    return _filtered_python_files(root)


def range_sort_key(range_value: Range) -> tuple[int, int, int, int]:
    """Build stable sort key for model ranges."""
    return (
        range_value.start.line,
        range_value.start.character,
        range_value.end.line,
        range_value.end.character,
    )


def apply_limit_items[T](items: list[T], limit: int | None) -> list[T]:
    """Apply an optional positive limit to list-style tool results."""
    from python_refactor_mcp.util.shared import apply_limit  # noqa: PLC0415

    limited, _ = apply_limit(items, limit)
    return limited


def name_position(line_text: str, default_col: int, name: str) -> int:
    """Find a symbol name offset in a source line with fallback to default."""
    index = line_text.find(name, max(default_col, 0))
    if index >= 0:
        return index
    return default_col


def is_test_file(path: Path) -> bool:
    """Return whether *path* follows a conventional Python test filename."""
    name = path.name
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def resolve_target_files(
    file_path: str | None,
    file_paths: list[str] | None,
    root_path: str | None,
    config: ServerConfig,
    exclude_test_files: bool,
) -> list[Path]:
    """Resolve the stable file set shared by workspace search scans."""
    if file_path is not None and file_paths is not None:
        raise ValueError("file_path and file_paths are mutually exclusive")
    effective_root = Path(root_path).resolve() if root_path else config.workspace_root
    if file_paths is not None:
        targets = [Path(path).resolve() for path in file_paths]
    elif file_path is not None:
        targets = [Path(file_path).resolve()]
    else:
        targets = python_files(effective_root)
    if exclude_test_files:
        targets = [path for path in targets if not is_test_file(path)]
    return targets


def score_dead_code_confidence(name: str, reason: str) -> str:
    """Score a dead-code candidate consistently across search tools."""
    if reason == "unused diagnostic":
        return "high"
    lower = name.lower()
    if lower in {"logger", "_logger", "log", "_log"}:
        return "low"
    if name.startswith(("test_", "Test")):
        return "low"
    if name.startswith("__") and name.endswith("__"):
        return "low"
    if name == "__all__":
        return "low"
    return "medium"


def _decorator_name(decorator: ast.expr) -> str:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    parts: list[str] = []
    while isinstance(target, ast.Attribute):
        parts.append(target.attr)
        target = target.value
    if isinstance(target, ast.Name):
        parts.append(target.id)
    return ".".join(reversed(parts))


def _explicit_exports(module: ast.Module) -> frozenset[str] | None:
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
            continue
        if isinstance(node.value, (ast.List, ast.Tuple)):
            return frozenset(
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
    return None


def scan_module_level_symbols(file_path: Path) -> ModuleSymbolScan:
    """Parse one module and return declarations without hiding read/parse failures."""
    source = file_path.read_text(encoding="utf-8")
    lines = source.splitlines()
    module = ast.parse(source, filename=str(file_path))
    symbols: list[ModuleLevelSymbol] = []

    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            line_index = node.lineno - 1
            if not 0 <= line_index < len(lines):
                continue
            char_index = name_position(lines[line_index], node.col_offset, node.name)
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            symbols.append(
                ModuleLevelSymbol(
                    name=node.name,
                    kind=kind,
                    range=Range(
                        start=Position(line=line_index, character=char_index),
                        end=Position(line=line_index, character=char_index + len(node.name)),
                    ),
                    decorator_names=tuple(
                        name for decorator in node.decorator_list if (name := _decorator_name(decorator))
                    ),
                )
            )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols.append(
                        ModuleLevelSymbol(
                            name=target.id,
                            kind="variable",
                            range=Range(
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
                ModuleLevelSymbol(
                    name=target.id,
                    kind="variable",
                    range=Range(
                        start=Position(line=target.lineno - 1, character=target.col_offset),
                        end=Position(
                            line=target.lineno - 1,
                            character=target.col_offset + len(target.id),
                        ),
                    ),
                )
            )

    return ModuleSymbolScan(symbols=tuple(symbols), explicit_exports=_explicit_exports(module))


def iter_module_level_symbols(
    file_path: Path,
    *,
    skip_decorated: bool,
) -> list[tuple[str, str, Range]]:
    """Return module declarations, optionally excluding every decorated symbol."""
    scan = scan_module_level_symbols(file_path)
    return [
        (symbol.name, symbol.kind, symbol.range)
        for symbol in scan.symbols
        if not skip_decorated or not symbol.decorator_names
    ]
