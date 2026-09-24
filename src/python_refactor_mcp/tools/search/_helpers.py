"""Shared helpers, protocols, and constants used across search submodules."""

from __future__ import annotations

import ast
import asyncio
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
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
    ScanFailure,
    SymbolInfo,
)
from python_refactor_mcp.util.file_filter import python_files as _filtered_python_files

DIAGNOSTIC_TAG_UNNECESSARY = 1

REFERENCE_SWEEP_CONCURRENCY = 10
"""Maximum in-flight Pyright requests per workspace sweep.

Pyright serves requests one at a time, so this bounds queue depth (and memory),
not throughput.
"""


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


# Whitespace plus every ASCII punctuation character except ``_``. An identifier token in
# valid Python source is always bounded by these (or by the start/end of the text).
_TOKEN_SEPARATORS = re.compile(r"[\s!-/:-@\[-\^`{-~]+")
_NON_ASCII_RUNS = re.compile(r"[^\x00-\x7f]+")
_INDEXED_SUFFIXES = (".py", ".pyi")


def _identifier_runs(piece: str) -> list[str]:
    """Split *piece* on every character that cannot continue a Python identifier."""
    runs: list[str] = []
    current: list[str] = []
    for char in piece:
        if ("a" + char).isidentifier():
            current.append(char)
        elif current:
            runs.append("".join(current))
            current = []
    if current:
        runs.append("".join(current))
    return runs


def _non_ascii_piece_names(piece: str) -> Counter[str]:
    """Count the names a tokenizer could read out of one piece containing non-ASCII text.

    Each candidate tokenization is counted separately and the per-name maximum is
    kept, so the result never undercounts any single tokenization: the raw piece,
    its runs of identifier characters, the NFKC-normalized forms of both (Python
    normalizes identifiers to NFKC, and ``ast`` reports normalized names), and the
    ASCII runs between non-ASCII characters.
    """
    runs = _identifier_runs(piece)
    tokenizations: list[list[str]] = [
        [piece],
        [unicodedata.normalize("NFKC", piece)],
        runs,
        [unicodedata.normalize("NFKC", run) for run in runs],
        [part for part in _NON_ASCII_RUNS.split(piece) if part],
    ]
    names: Counter[str] = Counter()
    for tokens in tokenizations:
        names |= Counter(tokens)
    return names


@dataclass(frozen=True, slots=True)
class NameOccurrenceIndex:
    """Per-file textual occurrence counts of candidate symbol names.

    Counts are a conservative superset of Pyright references: every reference
    Pyright can report is a token spelled with the symbol's name in some indexed
    file, so a name with no textual occurrence has no reference. The index only
    ever proves *absence*; any doubt falls back to a real reference query.

    Coverage limits (the index is only as complete as its file set):

    - Files are the ``*.py``/``*.pyi`` files under the workspace root, pruned by
      :func:`python_refactor_mcp.util.file_filter.python_files`' default directory
      exclusions (``.venv``, ``build``, ``dist``, ...), plus the scanned target files.
      A directory excluded there but included in the user's Pyright configuration
      (or a Pyright ``extraPaths`` entry outside the root) is not indexed, so a
      reference that exists only there is missed.
    - Contents are read from disk; a Pyright buffer holding unsaved edits that differ
      from disk is not seen.
    - Token boundaries assume valid Python source. Unreadable or non-UTF-8 files make
      the index ``complete=False``, which disables every shortcut.
    """

    occurrences: Mapping[str, Mapping[str, int]]
    complete: bool

    def mentioned_only_at_declaration(self, name: str, file_path: str) -> bool:
        """Return True when *name* occurs exactly once anywhere: its own declaration."""
        if not self.complete:
            return False
        return dict(self.occurrences.get(name, {})) == {file_path: 1}

    def mentioned_only_in(self, name: str, file_path: str) -> bool:
        """Return True when *name* occurs in *file_path* and in no other indexed file."""
        if not self.complete:
            return False
        return set(self.occurrences.get(name, {})) == {file_path}


def build_name_occurrence_index(
    workspace_root: Path,
    target_files: Iterable[Path],
    names: Iterable[str],
) -> NameOccurrenceIndex:
    """Count occurrences of *names* in every workspace Python file plus *target_files*.

    Blocking file I/O: call through ``asyncio.to_thread`` from async code. Files are
    keyed by ``str(path.resolve())``, matching the keys the sweeps use for the
    declaring file; a spelling mismatch only makes the index more conservative.
    """
    wanted = frozenset(names)
    occurrences: dict[str, dict[str, int]] = {}
    if not workspace_root.is_dir():
        return NameOccurrenceIndex(occurrences=occurrences, complete=False)
    files = {
        str(path.resolve()): path
        for path in [*_filtered_python_files(workspace_root, suffixes=_INDEXED_SUFFIXES), *target_files]
    }
    for key, path in files.items():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return NameOccurrenceIndex(occurrences={}, complete=False)
        file_counts: Counter[str] = Counter()
        for piece, count in Counter(_TOKEN_SEPARATORS.split(text)).items():
            if piece.isascii():
                if piece in wanted:
                    file_counts[piece] += count
                continue
            for name, name_count in _non_ascii_piece_names(piece).items():
                if name in wanted:
                    file_counts[name] += name_count * count
        for name, count in file_counts.items():
            occurrences.setdefault(name, {})[key] = count
    return NameOccurrenceIndex(occurrences=occurrences, complete=True)


async def sweep_name_occurrence_index(
    workspace_root: Path,
    target_files: list[Path],
    names: set[str],
    *,
    workspace_scan: bool,
) -> NameOccurrenceIndex:
    """Build the occurrence index off the event loop for a directory-wide sweep.

    The index reads every workspace file, a fixed cost that only pays for itself when
    the sweep has many candidates. A scan of explicit ``file_path``/``file_paths``
    targets (or one with no candidates) gets an incomplete index, which disables
    every shortcut, so each candidate is queried exactly as before.
    """
    if not workspace_scan or not names:
        return NameOccurrenceIndex(occurrences={}, complete=False)
    return await asyncio.to_thread(build_name_occurrence_index, workspace_root, target_files, names)


@dataclass(frozen=True, slots=True)
class ResolvedTargets:
    """Files a workspace search scan will inspect plus the requested scopes that do not exist."""

    files: list[Path]
    failures: list[ScanFailure]


def _resolve_failure(path: Path, wrong_kind_error: str) -> ScanFailure:
    """Describe a requested scan scope that does not exist or is the wrong kind of entry."""
    error_type = wrong_kind_error if path.exists() else "FileNotFoundError"
    return ScanFailure(file_path=str(path), phase="resolve", error_type=error_type)


def resolve_target_files(
    file_path: str | None,
    file_paths: list[str] | None,
    root_path: str | None,
    config: ServerConfig,
    exclude_test_files: bool,
) -> ResolvedTargets:
    """Resolve the stable file set shared by workspace search scans.

    A missing ``root_path`` or explicit file is returned as a ``phase="resolve"``
    failure so callers never report a nonexistent scope as a clean empty scan.
    """
    if file_path is not None and file_paths is not None:
        raise ValueError("file_path and file_paths are mutually exclusive")
    if file_paths is not None:
        requested = [Path(path).resolve() for path in file_paths]
    elif file_path is not None:
        requested = [Path(file_path).resolve()]
    else:
        effective_root = Path(root_path).resolve() if root_path else config.workspace_root
        if not effective_root.is_dir():
            return ResolvedTargets(files=[], failures=[_resolve_failure(effective_root, "NotADirectoryError")])
        requested = python_files(effective_root)
    if exclude_test_files:
        requested = [path for path in requested if not is_test_file(path)]
    files = [path for path in requested if path.is_file()]
    failures = [_resolve_failure(path, "IsADirectoryError") for path in requested if not path.is_file()]
    return ResolvedTargets(files=files, failures=failures)


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
