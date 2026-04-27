"""Unit tests for the LibCST apply foundation.

The foundation is tool-agnostic: every test below builds a tiny in-test
``cst.CSTTransformer`` and exercises the ``apply_cst_transformer`` /
``apply_cst_transformer_batch`` orchestrators. Real consumers
(``apply_type_annotations``, ``convert_to_dataclass``, etc.) layer on top.
"""

from __future__ import annotations

from pathlib import Path

import libcst as cst
import pytest

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.util.cst_apply import (
    apply_cst_transformer,
    apply_cst_transformer_batch,
    parse_module,
)


class _RenameNameTransformer(cst.CSTTransformer):
    """Rename every ``cst.Name`` whose value matches ``old`` to ``new``.

    Trivial enough that the test asserts the foundation's plumbing rather than
    transformer correctness.
    """

    def __init__(self, old: str, new: str) -> None:
        self.old = old
        self.new = new

    def leave_Name(  # noqa: N802 — LibCST visitor naming convention
        self, original_node: cst.Name, updated_node: cst.Name,
    ) -> cst.Name:
        if updated_node.value == self.old:
            return updated_node.with_changes(value=self.new)
        return updated_node


class _NoopTransformer(cst.CSTTransformer):
    """A transformer that visits every node and changes nothing."""


def test_parse_module_wraps_syntax_errors_with_file_context() -> None:
    """A LibCST parser error becomes a ``BackendError`` mentioning the file."""
    with pytest.raises(BackendError, match="Failed to parse /tmp/oops.py"):
        parse_module("def broken(:\n", "/tmp/oops.py")


def test_apply_cst_transformer_no_change_returns_empty(tmp_path: Path) -> None:
    """A transformer that does not mutate the tree yields no edits."""
    target = tmp_path / "m.py"
    target.write_text("x = 1\n", encoding="utf-8")

    edits, files = apply_cst_transformer(str(target), _NoopTransformer(), apply=False)

    assert edits == []
    assert files == []
    # Disk content untouched.
    assert target.read_text(encoding="utf-8") == "x = 1\n"


def test_apply_cst_transformer_emits_whole_file_replace(tmp_path: Path) -> None:
    """When the tree changes, exactly one whole-file replace edit is emitted."""
    target = tmp_path / "m.py"
    target.write_text("x = 1\ny = x\n", encoding="utf-8")

    edits, files = apply_cst_transformer(
        str(target),
        _RenameNameTransformer(old="x", new="renamed"),
        apply=False,
    )

    assert len(edits) == 1
    assert files == [str(target)]
    edit = edits[0]
    assert edit.file_path == str(target)
    assert edit.range.start.line == 0
    assert edit.range.start.character == 0
    assert edit.new_text == "renamed = 1\ny = renamed\n"
    # Preview mode — disk untouched.
    assert target.read_text(encoding="utf-8") == "x = 1\ny = x\n"


def test_apply_cst_transformer_apply_writes_atomically(tmp_path: Path) -> None:
    """``apply=True`` writes the new content to disk via the atomic helper."""
    target = tmp_path / "m.py"
    target.write_text("x = 1\n", encoding="utf-8")

    edits, files = apply_cst_transformer(
        str(target),
        _RenameNameTransformer(old="x", new="renamed"),
        apply=True,
    )

    assert len(edits) == 1
    assert files == [str(target)]
    assert target.read_text(encoding="utf-8") == "renamed = 1\n"


def test_apply_cst_transformer_missing_file_raises(tmp_path: Path) -> None:
    """A missing file surfaces as a ``BackendError`` with read-error context."""
    missing = tmp_path / "nope.py"
    with pytest.raises(BackendError, match="Cannot read file for CST transform"):
        apply_cst_transformer(str(missing), _NoopTransformer(), apply=False)


def test_apply_cst_transformer_batch_filters_unchanged(tmp_path: Path) -> None:
    """Batch mode only includes files the transformer actually changed."""
    dirty = tmp_path / "dirty.py"
    clean = tmp_path / "clean.py"
    dirty.write_text("x = 1\n", encoding="utf-8")
    clean.write_text("y = 2\n", encoding="utf-8")

    def factory(_path: str) -> cst.CSTTransformer:
        return _RenameNameTransformer(old="x", new="renamed")

    edits, files = apply_cst_transformer_batch(
        [str(dirty), str(clean)],
        factory,
        apply=False,
    )

    assert len(edits) == 1
    assert files == [str(dirty)]
    assert edits[0].file_path == str(dirty)


def test_apply_cst_transformer_batch_factory_invoked_per_file(tmp_path: Path) -> None:
    """The factory receives each file path and is called once per file."""
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("x = 2\n", encoding="utf-8")
    seen: list[str] = []

    def factory(path: str) -> cst.CSTTransformer:
        seen.append(path)
        return _RenameNameTransformer(old="x", new="z")

    edits, files = apply_cst_transformer_batch(
        [str(a), str(b)],
        factory,
        apply=True,
    )

    assert seen == [str(a), str(b)]
    assert len(edits) == 2
    assert files == sorted([str(a), str(b)])
    assert a.read_text(encoding="utf-8") == "z = 1\n"
    assert b.read_text(encoding="utf-8") == "z = 2\n"


def test_apply_cst_transformer_propagates_parse_errors(tmp_path: Path) -> None:
    """A file that fails to parse surfaces as a ``BackendError`` mentioning it."""
    target = tmp_path / "broken.py"
    target.write_text("def oops(:\n", encoding="utf-8")  # syntax error

    with pytest.raises(BackendError, match=r"Failed to parse .*broken\.py"):
        apply_cst_transformer(str(target), _NoopTransformer(), apply=False)
