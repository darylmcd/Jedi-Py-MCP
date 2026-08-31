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
from dataclasses import dataclass
from pathlib import Path

import libcst as cst
from libcst.metadata import MetadataWrapper

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import Position, Range, TextEdit
from python_refactor_mcp.util.diff import (
    apply_text_edits_atomically,
    write_atomic_if_unchanged,
)
from python_refactor_mcp.util.shared import end_position_for_content


@dataclass(frozen=True)
class CstSourceSnapshot:
    """One parsed source snapshot shared by semantic planning and CST emission."""

    file_path: str
    source: str
    source_bytes: bytes
    module: cst.Module


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


def read_cst_source_snapshot(file_path: str) -> CstSourceSnapshot:
    """Read and parse *file_path* once for a snapshot-coherent CST operation."""
    path = Path(file_path).resolve()
    try:
        source_bytes = path.read_bytes()
        # Match ``Path.read_text``'s universal-newline behavior while retaining
        # the exact bytes for optimistic-concurrency checks.
        source = source_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except (FileNotFoundError, OSError, UnicodeError) as exc:
        raise BackendError(f"Cannot read file for CST transform: {exc}") from exc

    return CstSourceSnapshot(
        file_path=str(path),
        source=source,
        source_bytes=source_bytes,
        module=parse_module(source, file_path),
    )


def _verify_snapshot_current(snapshot: CstSourceSnapshot) -> None:
    try:
        current_bytes = Path(snapshot.file_path).read_bytes()
    except OSError as exc:
        raise BackendError(f"Cannot verify CST source snapshot: {exc}") from exc
    if current_bytes != snapshot.source_bytes:
        raise BackendError(
            f"Stale edit source changed during CST planning: {snapshot.file_path}"
        )


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
    source_snapshot: CstSourceSnapshot | None = None,
) -> tuple[list[TextEdit], list[str], bytes]:
    """Build one CST transform and retain the exact source bytes it consumed."""
    snapshot = source_snapshot or read_cst_source_snapshot(file_path)
    if Path(file_path).resolve() != Path(snapshot.file_path):
        raise BackendError("CST source snapshot does not match the transform target")

    # Check on both sides of the potentially expensive transformation. This
    # rejects drift that occurs during async semantic planning or CST traversal
    # before a preview is emitted; apply mode retains its atomic write guard too.
    _verify_snapshot_current(snapshot)
    new_module = MetadataWrapper(snapshot.module, unsafe_skip_copy=True).visit(transformer)
    new_source = new_module.code
    _verify_snapshot_current(snapshot)

    if new_source == snapshot.source:
        return ([], [], snapshot.source_bytes)

    edit = _whole_file_edit(file_path, snapshot.source, new_source)
    return ([edit], [file_path], snapshot.source_bytes)


def apply_cst_transformer(
    file_path: str,
    transformer: cst.CSTTransformer,
    *,
    apply: bool = False,
    source_snapshot: CstSourceSnapshot | None = None,
) -> tuple[list[TextEdit], list[str]]:
    """Read *file_path*, run *transformer*, return ``(edits, files_affected)``.

    The transformer instance is consumed once. If the transformer does not
    change the source (string-equal output), the result is empty — no edit, no
    file mutation, no entry in ``files_affected``. When ``apply`` is True the
    exact source bytes are checked again immediately before the atomic replace;
    stale transforms fail without overwriting the newer source. Pass a
    ``source_snapshot`` when semantic planning preceded transformation so the
    plan, preview, and optional write are bound to the same parsed source.

    Wrap the returned ``edits`` and ``files_affected`` into a ``RefactorResult``
    in the caller; if the result is non-empty pass it through
    ``post_apply_diagnostics`` so Pyright sees the new content.
    """
    edits, files_affected, original_bytes = _build_cst_transform(
        file_path,
        transformer,
        source_snapshot,
    )

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
    "CstSourceSnapshot",
    "apply_cst_transformer",
    "apply_cst_transformer_batch",
    "parse_module",
    "read_cst_source_snapshot",
]
