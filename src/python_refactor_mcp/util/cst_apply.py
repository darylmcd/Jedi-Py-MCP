"""Foundation for LibCST-based code mutations that fit the preview/apply contract.

This module provides the parse → transform → emit cycle that backs every custom-CST
refactoring tool in this codebase (for example ``extract_superclass`` and
``convert_to_dataclass``). The contract mirrors the rope/format paths:

* Each successful transformation produces one **whole-file replace** ``TextEdit``
  (CST transformations naturally rewrite the entire module, and our existing
  ``apply_text_edits`` already serializes them through the same edit shape).
* Files where the transformer makes no change are dropped — they yield no edit
  and do not appear in ``files_affected``.
* On ``apply=True`` the source is revalidated and the new content is written
  through a guarded atomic replace; the caller is responsible for the
  post-apply ``notify_file_changed`` / diagnostics step (use
  ``tools.refactoring.helpers.post_apply_diagnostics``).

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
from python_refactor_mcp.util.diff import (
    apply_text_edits_atomically,
    write_atomic_if_unchanged,
)
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


def _build_cst_transform(
    file_path: str,
    transformer: cst.CSTTransformer,
) -> tuple[list[TextEdit], list[str], bytes]:
    """Build one CST transform and retain the exact source bytes it consumed."""
    try:
        original_bytes = Path(file_path).read_bytes()
        # Match ``Path.read_text``'s universal-newline behavior while retaining
        # the exact bytes separately for the optimistic-concurrency guard.
        original = original_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except (FileNotFoundError, OSError, UnicodeError) as exc:
        raise BackendError(f"Cannot read file for CST transform: {exc}") from exc

    module = parse_module(original, file_path)
    new_module = module.visit(transformer)
    new_source = new_module.code

    if new_source == original:
        return ([], [], original_bytes)

    edit = _whole_file_edit(file_path, original, new_source)
    return ([edit], [file_path], original_bytes)


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
    exact source bytes are checked again immediately before the atomic replace;
    stale transforms fail without overwriting the newer source.

    Wrap the returned ``edits`` and ``files_affected`` into a ``RefactorResult``
    in the caller; if the result is non-empty pass it through
    ``post_apply_diagnostics`` so Pyright sees the new content.
    """
    edits, files_affected, original_bytes = _build_cst_transform(file_path, transformer)

    if apply and edits:
        write_atomic_if_unchanged(file_path, edits[0].new_text, original_bytes)

    return (edits, files_affected)


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
    expected_contents: dict[str, bytes] = {}

    for fp in file_paths:
        # Build every edit before writing so a later parse/transform failure
        # cannot leave earlier files mutated.
        file_edits, file_changed, original_bytes = _build_cst_transform(fp, transformer_factory(fp))
        edits.extend(file_edits)
        files_affected.extend(file_changed)
        if file_changed:
            expected_contents[fp] = original_bytes

    files_affected = sorted(set(files_affected))
    if apply and edits:
        apply_text_edits_atomically(edits, expected_contents=expected_contents)
    return (edits, files_affected)


__all__ = [
    "apply_cst_transformer",
    "apply_cst_transformer_batch",
    "parse_module",
]
