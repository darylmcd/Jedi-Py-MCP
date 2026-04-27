"""Type-user discovery tool — inverse of ``find_references`` scoped to a type.

Composes :func:`find_references` (semantic site discovery via Pyright+Jedi) with an
AST-based per-site classifier. Each reference is bucketed as ``annotation`` (type-hint
position), ``instantiation`` (head of a call), ``subclass`` (a ``ClassDef.bases``
entry), or ``other``.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from python_refactor_mcp.models import TypeUserSite, TypeUsersResult
from python_refactor_mcp.tools.analysis._protocols import (
    JediAnalysisBackend as _JediAnalysisBackend,
)
from python_refactor_mcp.tools.analysis._protocols import (
    PyrightAnalysisBackend as _PyrightAnalysisBackend,
)
from python_refactor_mcp.tools.analysis.references import find_references
from python_refactor_mcp.util.shared import apply_limit

_LOGGER = logging.getLogger(__name__)

ALL_KINDS: frozenset[str] = frozenset({"annotation", "instantiation", "subclass", "other"})


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    """Map each AST node's id() to its parent for parent-chain walking."""
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _annotation_root_ids(tree: ast.AST) -> set[int]:
    """Collect the id()s of every AST subtree root that is a type-annotation expression."""
    roots: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                roots.add(id(node.returns))
            args = node.args
            for arg in (
                *args.args,
                *args.posonlyargs,
                *args.kwonlyargs,
                args.vararg,
                args.kwarg,
            ):
                if arg is not None and arg.annotation is not None:
                    roots.add(id(arg.annotation))
        elif isinstance(node, ast.AnnAssign):
            # AnnAssign.annotation is always present in the AST schema.
            roots.add(id(node.annotation))
    return roots


def _subclass_base_ids(tree: ast.AST) -> set[int]:
    """Collect the id()s of every base expression in a ``ClassDef.bases`` list."""
    bases: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                bases.add(id(base))
    return bases


def _ancestor_in(node: ast.AST, parents: dict[int, ast.AST], targets: set[int]) -> bool:
    """Return True if ``node`` or any ancestor's id() is in ``targets``."""
    cur: ast.AST | None = node
    while cur is not None:
        if id(cur) in targets:
            return True
        cur = parents.get(id(cur))
    return False


def _find_identifier_at(tree: ast.AST, line: int, character: int) -> ast.AST | None:
    """Find the smallest ``Name``/``Attribute`` node whose location matches (line, character).

    LSP/Pyright positions are 0-based; ``ast`` line numbers are 1-based and column offsets
    are 0-based byte offsets. Match Name nodes by start position, and Attribute nodes by
    the end position of the attribute name (since the location may point at the attribute
    portion of e.g. ``pkg.Foo``).
    """
    target_line = line + 1  # convert to 1-based
    best: ast.AST | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.lineno == target_line and node.col_offset == character:
                return node
        elif isinstance(node, ast.Attribute) and node.end_lineno == target_line:
            # Pyright tends to point at the attribute name token; estimate its column
            # as the end_col_offset minus len(attr).
            attr_start = (node.end_col_offset or 0) - len(node.attr)
            if attr_start == character:
                best = node
    return best


def _classify_site(
    tree: ast.AST,
    parents: dict[int, ast.AST],
    annotation_roots: set[int],
    subclass_bases: set[int],
    line: int,
    character: int,
) -> str:
    """Classify a reference at (line, character) into one of the four buckets."""
    node = _find_identifier_at(tree, line, character)
    if node is None:
        return "other"

    if _ancestor_in(node, parents, annotation_roots):
        return "annotation"
    if _ancestor_in(node, parents, subclass_bases):
        return "subclass"

    # Instantiation: walk up across Attribute chains; if first non-Name/non-Attribute
    # ancestor is a Call and the node sits in Call.func, classify as instantiation.
    cur: ast.AST = node
    while True:
        parent = parents.get(id(cur))
        if parent is None:
            break
        if isinstance(parent, ast.Call):
            if parent.func is cur:
                return "instantiation"
            break
        if not isinstance(parent, ast.Attribute):
            break
        cur = parent
    return "other"


def _read_and_parse(
    file_path: str,
    cache: dict[str, tuple[ast.AST, list[str]] | None],
) -> tuple[ast.AST, list[str]] | None:
    """Read+parse a file once per call, caching the result (None on failure)."""
    if file_path in cache:
        return cache[file_path]
    try:
        source = Path(file_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        _LOGGER.debug("type_users: failed to read/parse %s", file_path, exc_info=True)
        cache[file_path] = None
        return None
    cache[file_path] = (tree, source.splitlines())
    return cache[file_path]


def _context_line(lines: list[str], line: int) -> str | None:
    if 0 <= line < len(lines):
        return lines[line].rstrip("\r\n")
    return None


async def find_type_users(
    pyright: _PyrightAnalysisBackend,
    jedi: _JediAnalysisBackend,
    file_path: str,
    line: int,
    character: int,
    kinds: list[str] | None = None,
    include_declaration: bool = False,
    limit: int | None = None,
) -> TypeUsersResult:
    """Inverse of ``find_references`` scoped to a type.

    Returns each reference site classified as ``annotation``, ``instantiation``,
    ``subclass``, or ``other``. ``kinds`` filters the returned sites (case-insensitive);
    ``by_kind`` always reports counts for every bucket. Default ``include_declaration``
    is False — class/Protocol definitions are usually not interesting type *uses*.
    """
    if kinds is not None:
        normalized_kinds = {k.lower() for k in kinds}
        unknown = normalized_kinds - ALL_KINDS
        if unknown:
            raise ValueError(
                f"Unknown kinds {sorted(unknown)}. Valid: {sorted(ALL_KINDS)}",
            )
    else:
        normalized_kinds = set(ALL_KINDS)

    refs = await find_references(
        pyright,
        jedi,
        file_path,
        line,
        character,
        include_declaration=include_declaration,
        include_context=False,
        limit=None,  # apply our own limit after classification
    )

    by_kind: dict[str, int] = {kind: 0 for kind in sorted(ALL_KINDS)}
    sites: list[TypeUserSite] = []
    parse_cache: dict[str, tuple[ast.AST, list[str]] | None] = {}

    for location in refs.references:
        parsed = _read_and_parse(location.file_path, parse_cache)
        if parsed is None:
            kind = "other"
            ctx_line: str | None = None
        else:
            tree, source_lines = parsed
            parents = _build_parent_map(tree)
            annotation_roots = _annotation_root_ids(tree)
            subclass_bases = _subclass_base_ids(tree)
            kind = _classify_site(
                tree,
                parents,
                annotation_roots,
                subclass_bases,
                location.range.start.line,
                location.range.start.character,
            )
            ctx_line = _context_line(source_lines, location.range.start.line)

        by_kind[kind] += 1
        if kind in normalized_kinds:
            sites.append(
                TypeUserSite(location=location, kind=kind, context=ctx_line),
            )

    total_count = len(sites)
    sites, truncated = apply_limit(sites, limit)

    symbol = refs.symbol
    return TypeUsersResult(
        symbol=symbol,
        sites=sites,
        by_kind=by_kind,
        total_count=total_count,
        source=refs.source,
        truncated=truncated,
    )


__all__ = ["ALL_KINDS", "find_type_users"]
