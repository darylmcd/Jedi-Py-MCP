"""Search tools for constructor sites, structural patterns, dead code, and imports."""

from __future__ import annotations

import ast
import asyncio
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

import libcst as cst
from libcst import matchers as m
from libcst.metadata import CodeRange, MetadataWrapper, PositionProvider

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    ConstructorSite,
    DeadCodeItem,
    Diagnostic,
    ImportSuggestion,
    Location,
    Position,
    Range,
    StructuralMatch,
    SymbolInfo,
)

_DIAGNOSTIC_TAG_UNNECESSARY = 1


class _PyrightSearchBackend(Protocol):
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


class _JediSearchBackend(Protocol):
    """Protocol describing Jedi search methods used by this module."""

    async def search_names(self, symbol: str) -> list[ImportSuggestion]:
        """Search names and convert them into import suggestions."""
        ...

    async def search_symbols(self, query: str) -> list[SymbolInfo]:
        """Search project symbols by query string."""
        ...


_UNRESOLVED_PATTERNS = (
    "is not defined",
    "cannot be resolved",
    "unknown import symbol",
    "name",
)


def _python_files(root: Path) -> list[Path]:
    """Return Python files below a root path in stable order."""
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _range_sort_key(range_value: Range) -> tuple[int, int, int, int]:
    """Build stable sort key for model ranges."""
    return (
        range_value.start.line,
        range_value.start.character,
        range_value.end.line,
        range_value.end.character,
    )


def _symbol_sort_key(symbol: SymbolInfo) -> tuple[str, str, int, int, str]:
    """Build stable sort key for symbol search results."""
    return (
        symbol.file_path,
        symbol.name,
        symbol.range.start.line,
        symbol.range.start.character,
        symbol.kind,
    )


def _apply_limit[T](items: list[T], limit: int | None) -> list[T]:
    """Apply an optional positive limit to list-style tool results."""
    if limit is None:
        return items
    if limit < 1:
        raise ValueError("limit must be greater than or equal to 1")
    return items[:limit]


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


def _name_position(line_text: str, default_col: int, name: str) -> int:
    """Find a symbol name offset in a source line with fallback to default."""
    index = line_text.find(name, max(default_col, 0))
    if index >= 0:
        return index
    return default_col


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
        for node in module.body:
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


def _as_import_suggestion(symbol: str, statement: str) -> ImportSuggestion | None:
    """Parse an import statement into an import suggestion model."""
    normalized = statement.strip()
    from_match = re.match(r"from\s+([\w.]+)\s+import\s+(.+)", normalized)
    if from_match:
        return ImportSuggestion(
            symbol=symbol,
            module=from_match.group(1),
            import_statement=normalized,
        )

    import_match = re.match(r"import\s+([\w.]+)", normalized)
    if import_match:
        return ImportSuggestion(
            symbol=symbol,
            module=import_match.group(1),
            import_statement=normalized,
        )

    return None


def _extract_import_lines_from_action(action: dict[str, object], symbol: str) -> list[ImportSuggestion]:
    """Extract import suggestions from a code action payload."""
    suggestions: list[ImportSuggestion] = []
    candidates: list[str] = []

    title = action.get("title")
    if isinstance(title, str):
        candidates.extend(re.findall(r"(?:from\s+[\w.]+\s+import\s+[^\n]+|import\s+[\w.]+)", title))

    edit = action.get("edit")
    if isinstance(edit, dict):
        changes = edit.get("changes")
        if isinstance(changes, dict):
            for value in changes.values():
                if not isinstance(value, list):
                    continue
                for entry in value:
                    if not isinstance(entry, dict):
                        continue
                    new_text = entry.get("newText")
                    if isinstance(new_text, str):
                        candidates.extend(
                            re.findall(
                                r"(?:from\s+[\w.]+\s+import\s+[^\n]+|import\s+[\w.]+)",
                                new_text,
                            )
                        )

    for candidate in candidates:
        suggestion = _as_import_suggestion(symbol, candidate)
        if suggestion is not None:
            suggestions.append(suggestion)
    return suggestions


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


async def search_symbols(
    pyright: _PyrightSearchBackend,
    jedi: _JediSearchBackend,
    query: str,
    limit: int | None = None,
) -> list[SymbolInfo]:
    """Search workspace symbols by name across both semantic backends."""
    merged: dict[tuple[str, str, int, int, str], SymbolInfo] = {}

    try:
        pyright_symbols = await pyright.workspace_symbol(query)
    except Exception:
        pyright_symbols = []
    for symbol in pyright_symbols:
        merged[_symbol_sort_key(symbol)] = symbol

    try:
        jedi_symbols = await jedi.search_symbols(query)
    except Exception:
        jedi_symbols = []
    for symbol in jedi_symbols:
        merged.setdefault(_symbol_sort_key(symbol), symbol)

    sorted_items = sorted(merged.values(), key=_symbol_sort_key)
    return _apply_limit(sorted_items, limit)


async def structural_search(
    config: ServerConfig,
    pattern: str,
    file_path: str | None = None,
    language: str = "python",
    limit: int | None = None,
) -> list[StructuralMatch]:
    """Run LibCST matcher-based structural search for Python code."""
    if language.strip().lower() != "python":
        raise ValueError("Only language='python' is supported.")

    try:
        matcher = eval(pattern, {"__builtins__": {}}, {"m": m, "cst": cst})
    except Exception as exc:
        raise ValueError("Invalid LibCST matcher pattern.") from exc
    if not isinstance(matcher, m.BaseMatcherNode):
        raise ValueError("Pattern must evaluate to a LibCST matcher node.")

    candidate_files = [Path(file_path).resolve()] if file_path is not None else _python_files(config.workspace_root)

    def _scan_file(path: Path) -> list[StructuralMatch]:
        source = path.read_text(encoding="utf-8")
        module = cst.parse_module(source)
        wrapper = MetadataWrapper(module)

        class _Collector(cst.CSTVisitor):
            METADATA_DEPENDENCIES = (PositionProvider,)

            def __init__(self) -> None:
                self.matches: list[StructuralMatch] = []

            def on_visit(self, node: cst.CSTNode) -> bool:
                if not m.matches(node, matcher):
                    return True
                code_range = self.get_metadata(PositionProvider, node)
                if not isinstance(code_range, CodeRange):
                    return True
                self.matches.append(
                    StructuralMatch(
                        file_path=str(path.resolve()),
                        range=Range(
                            start=Position(
                                line=code_range.start.line - 1,
                                character=code_range.start.column,
                            ),
                            end=Position(
                                line=code_range.end.line - 1,
                                character=code_range.end.column,
                            ),
                        ),
                        matched_text=module.code_for_node(node),
                    )
                )
                return True

        collector = _Collector()
        wrapper.visit(collector)
        return collector.matches

    all_matches = await asyncio.gather(*[asyncio.to_thread(_scan_file, path) for path in candidate_files])
    flattened = [item for group in all_matches for item in group]
    sorted_items = sorted(flattened, key=lambda item: (item.file_path, *_range_sort_key(item.range)))
    return _apply_limit(sorted_items, limit)


async def dead_code_detection(
    pyright: _PyrightSearchBackend,
    config: ServerConfig,
    file_path: str | None = None,
    exclude_patterns: list[str] | None = None,
) -> list[DeadCodeItem]:
    """Detect dead code candidates using diagnostics and reference counts."""
    target_files = [Path(file_path).resolve()] if file_path is not None else _python_files(config.workspace_root)

    dead_items: dict[tuple[str, str, int, int], DeadCodeItem] = {}

    compiled_excludes = [re.compile(pattern) for pattern in (exclude_patterns or [])]

    diagnostics = await pyright.get_diagnostics(file_path)
    for diagnostic in diagnostics:
        lowered = diagnostic.message.lower()
        has_unnecessary_tag = _DIAGNOSTIC_TAG_UNNECESSARY in diagnostic.tags
        if not has_unnecessary_tag and "unused" not in lowered and "not accessed" not in lowered:
            continue

        quoted = re.findall(r"['\"]([^'\"]+)['\"]", diagnostic.message)
        name = quoted[0] if quoted else "unknown"
        item = DeadCodeItem(
            name=name,
            kind="import" if "import" in lowered else "symbol",
            file_path=diagnostic.file_path,
            range=diagnostic.range,
            reason="unused diagnostic",
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
            external_refs = []
            for ref in references:
                ref_path = getattr(ref, "file_path", None)
                if not isinstance(ref_path, str):
                    continue
                if ref_path != str(path.resolve()):
                    external_refs.append(ref)
            if references and external_refs:
                continue

            item = DeadCodeItem(
                name=name,
                kind=kind,
                file_path=str(path.resolve()),
                range=symbol_range,
                reason="no references",
            )
            key = (item.file_path, item.name, item.range.start.line, item.range.start.character)
            dead_items[key] = item

    return sorted(
        dead_items.values(),
        key=lambda item: (
            item.file_path,
            item.name,
            item.range.start.line,
            item.range.start.character,
        ),
    )


async def suggest_imports(
    pyright: _PyrightSearchBackend,
    jedi: _JediSearchBackend,
    symbol: str,
    file_path: str,
) -> list[ImportSuggestion]:
    """Suggest imports for an unresolved symbol in a file context."""
    diagnostics = await pyright.get_diagnostics(file_path)
    unresolved = [
        diagnostic
        for diagnostic in diagnostics
        if symbol in diagnostic.message
        and any(pattern in diagnostic.message.lower() for pattern in _UNRESOLVED_PATTERNS)
    ]

    pyright_suggestions: list[ImportSuggestion] = []
    for diagnostic in unresolved:
        actions = await pyright.get_code_actions(file_path, diagnostic.range, [diagnostic])
        for action in actions:
            pyright_suggestions.extend(_extract_import_lines_from_action(action, symbol))

    if not pyright_suggestions:
        pyright_suggestions = []

    jedi_suggestions = await jedi.search_names(symbol)

    deduped: dict[tuple[str, str], ImportSuggestion] = {}
    for suggestion in pyright_suggestions + jedi_suggestions:
        key = (suggestion.symbol, suggestion.module)
        if key not in deduped:
            deduped[key] = suggestion

    return sorted(deduped.values(), key=lambda item: (item.module, item.import_statement))
