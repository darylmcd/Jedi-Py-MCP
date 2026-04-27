"""Foundation for LibCST-based code mutations that fit the preview/apply contract.

This module provides the parse → transform → emit cycle that backs every custom-CST
refactoring tool in this codebase (e.g. ``apply_type_annotations``,
``convert_to_dataclass``, ``extract_class``, ``convert_function_to_method``,
``split_module``). The contract mirrors the rope/format paths:

* Each successful transformation produces one **whole-file replace** ``TextEdit``
  (CST transformations naturally rewrite the entire module, and our existing
  ``apply_text_edits`` already serializes them through the same edit shape).
* Files where the transformer makes no change are dropped — they yield no edit
  and do not appear in ``files_affected``.
* On ``apply=True`` the new content is written via ``write_atomic``; the caller
  is responsible for the post-apply ``notify_file_changed`` / diagnostics step
  (use ``tools.refactoring.helpers.post_apply_diagnostics``).

Concrete consumers compose: build a ``cst.CSTTransformer`` that performs the
edit (or a factory mapping a file path to a transformer for the batch case),
hand it to one of the orchestrators below, then wrap the returned edits into a
``RefactorResult`` for return.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import libcst as cst

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import Position, Range, TextEdit
from python_refactor_mcp.util.diff import write_atomic
from python_refactor_mcp.util.shared import end_position_for_content


def parse_module(source: str, file_path: str) -> cst.Module:
    """Parse *source* as a LibCST ``Module`` with file-aware error wrapping.

    Raises ``BackendError`` (not LibCST's native ``ParserSyntaxError``) so the
    server-level boundary surfaces a uniform error shape across all CST-based
    tools.
    """
    try:
        return cst.parse_module(source)
    except cst.ParserSyntaxError as exc:
        raise BackendError(f"Failed to parse {file_path} as Python source: {exc}") from exc


def _whole_file_edit(file_path: str, original: str, new_source: str) -> TextEdit:
    """Build a single whole-file replace ``TextEdit`` covering the original content."""
    return TextEdit(
        file_path=file_path,
        range=Range(start=Position(line=0, character=0), end=end_position_for_content(original)),
        new_text=new_source,
    )


def apply_cst_transformer(
    file_path: str,
    transformer: cst.CSTTransformer,
    *,
    apply: bool = False,
) -> tuple[list[TextEdit], list[str]]:
    """Read *file_path*, run *transformer*, return ``(edits, files_affected)``.

    The transformer instance is consumed once. If the transformer does not
    change the source (string-equal output), the result is empty — no edit, no
    file mutation, no entry in ``files_affected``. When ``apply`` is True the
    new content is written atomically.

    Wrap the returned ``edits`` and ``files_affected`` into a ``RefactorResult``
    in the caller; if the result is non-empty pass it through
    ``post_apply_diagnostics`` so Pyright sees the new content.
    """
    try:
        original = Path(file_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise BackendError(f"Cannot read file for CST transform: {exc}") from exc

    module = parse_module(original, file_path)
    new_module = module.visit(transformer)
    new_source = new_module.code

    if new_source == original:
        return ([], [])

    edit = _whole_file_edit(file_path, original, new_source)

    if apply:
        write_atomic(file_path, new_source)

    return ([edit], [file_path])


def apply_cst_transformer_batch(
    file_paths: list[str],
    transformer_factory: Callable[[str], cst.CSTTransformer],
    *,
    apply: bool = False,
) -> tuple[list[TextEdit], list[str]]:
    """Apply a fresh transformer (built per-file) to every path; collect changes.

    The factory is invoked once per file path and MUST return a fresh
    transformer instance — LibCST visitors carry per-traversal state, so reuse
    across files leaks state. Files where the transformer makes no change are
    silently dropped.
    """
    edits: list[TextEdit] = []
    files_affected: list[str] = []

    for fp in file_paths:
        file_edits, file_changed = apply_cst_transformer(
            fp, transformer_factory(fp), apply=apply,
        )
        edits.extend(file_edits)
        files_affected.extend(file_changed)

    files_affected = sorted(set(files_affected))
    return (edits, files_affected)


__all__ = [
    "apply_cst_transformer",
    "apply_cst_transformer_batch",
    "parse_module",
]
