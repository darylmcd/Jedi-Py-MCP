"""Applying edits keeps each file's own line endings (CRLF, lone CR, mixed, BOM).

Edit planning reads files as universal-newline text, so planned text uses ``\\n``.
Every writer must put the file's endings back; assertions are on the bytes on disk.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import libcst as cst
import pytest

from python_refactor_mcp.backends import rope_backend as rope_backend_module
from python_refactor_mcp.backends.rope_backend import RopeBackend
from python_refactor_mcp.errors import RopeError
from python_refactor_mcp.models import Position, Range, SignatureOperation, TextEdit
from python_refactor_mcp.tools import refactoring
from python_refactor_mcp.tools.refactoring import format as format_mod
from python_refactor_mcp.tools.refactoring.helpers import result_from_text_edits
from python_refactor_mcp.util import diff as diff_module
from python_refactor_mcp.util.cst_apply import apply_cst_transformer, apply_cst_transformer_batch
from python_refactor_mcp.util.diff import (
    apply_text_edits_atomically,
    encode_with_line_endings,
    write_atomic,
    write_atomic_if_unchanged,
)
from tests.helpers import make_config

_STYLES = {"crlf": "\r\n", "cr": "\r"}


def _edit(path: Path, start: tuple[int, int], end: tuple[int, int], text: str) -> TextEdit:
    return TextEdit(
        file_path=str(path),
        range=Range(start=Position(line=start[0], character=start[1]), end=Position(line=end[0], character=end[1])),
        new_text=text,
    )


def _backend(tmp_path: Path) -> RopeBackend:
    backend = RopeBackend(make_config(tmp_path))
    backend.initialize()
    return backend


# --- encode_with_line_endings -------------------------------------------------

_ENCODE_CASES = [
    pytest.param(b"a\nb\n", "a\nc\n", b"a\nc\n", id="lf"),
    pytest.param(b"a\r\nb\r\n", "a\nc\nd\n", b"a\r\nc\r\nd\r\n", id="crlf-grows"),
    pytest.param(b"a\rb\r", "a\nx\ny\n", b"a\rx\ry\r", id="lone-cr"),
    pytest.param(b"a\r\nb", "a\nb\nc", b"a\r\nb\r\nc", id="crlf-no-final-newline"),
    pytest.param(b"a\r\nb", "a\nb\n", b"a\r\nb\r\n", id="crlf-gains-final-newline"),
    pytest.param(b"a\r\nb\r\n", "a\nb", b"a\r\nb", id="crlf-loses-final-newline"),
    pytest.param(b"a\r\nb\r\n", "a\r\nx\ry\n", b"a\r\nx\r\ny\r\n", id="new-text-endings-are-normalised"),
    pytest.param(b"\xef\xbb\xbfa\r\nb\r\n", "\ufeffa\nc\n", b"\xef\xbb\xbfa\r\nc\r\n", id="bom-crlf"),
    pytest.param(b"", "a\nb\n", b"a\nb\n", id="empty-original"),
    pytest.param(b"a", "a\nb\n", b"a\nb\n", id="no-terminator-original"),
    pytest.param(b"a\r\nb\nc\r\n", "a\nB\nc\n", b"a\r\nB\nc\r\n", id="mixed-changed-line-keeps-its-own-ending"),
    pytest.param(b"a\r\nb\nc\r\n", "a\nb\nc\n", b"a\r\nb\nc\r\n", id="mixed-unchanged-lines-keep-endings"),
    pytest.param(b"a\r\nb\r\nc\n", "a\nNEW\nb\nc\n", b"a\r\nNEW\r\nb\r\nc\n", id="mixed-insert-takes-dominant"),
    pytest.param(b"a\nb\r\n", "a\nb\nNEW\n", b"a\nb\r\nNEW\n", id="mixed-dominant-tie-goes-to-first-seen"),
    pytest.param(b"a\r\nb\nc\rd\r\n", "a\nd\n", b"a\r\nd\r\n", id="mixed-deleted-middle"),
]


@pytest.mark.parametrize(("original", "new_text", "expected"), _ENCODE_CASES)
def test_encode_with_line_endings(original: bytes, new_text: str, expected: bytes) -> None:
    assert encode_with_line_endings(original, new_text) == expected


_REORDERED = (b"a\r\nb\nc\r\nd\n", "a\nZ\nc\nb\nd\n")


def test_encode_pairs_changed_lines_by_line_diff() -> None:
    assert encode_with_line_endings(*_REORDERED) == b"a\r\nZ\r\nc\r\nb\nd\n"


def test_encode_pairs_changed_lines_by_position_when_the_diff_would_be_too_large(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(diff_module, "_MAX_DIFF_CELLS", 0)
    assert encode_with_line_endings(*_REORDERED) == b"a\r\nZ\nc\r\nb\r\nd\n"


# --- text writers --------------------------------------------------------------


@pytest.mark.parametrize("style", ["\r\n", "\r", "\n"])
def test_write_atomic_keeps_the_targets_line_endings(tmp_path: Path, style: str) -> None:
    target = tmp_path / "m.py"
    target.write_bytes(f"a = 1{style}b = 2{style}".encode())
    write_atomic(str(target), "a = 10\nb = 2\nc = 3\n")
    assert target.read_bytes() == f"a = 10{style}b = 2{style}c = 3{style}".encode()


def test_write_atomic_writes_lf_to_a_new_file(tmp_path: Path) -> None:
    target = tmp_path / "new.py"
    write_atomic(str(target), "a = 1\nb = 2\n")
    assert target.read_bytes() == b"a = 1\nb = 2\n"


def test_write_atomic_if_unchanged_follows_the_expected_bytes(tmp_path: Path) -> None:
    target = tmp_path / "m.py"
    original = b"\xef\xbb\xbfa = 1\r\nb = 2\r\n"
    target.write_bytes(original)
    write_atomic_if_unchanged(str(target), "\ufeffa = 10\nb = 2\n", original)
    assert target.read_bytes() == b"\xef\xbb\xbfa = 10\r\nb = 2\r\n"


def test_write_atomic_if_unchanged_still_refuses_a_stale_target(tmp_path: Path) -> None:
    target = tmp_path / "m.py"
    target.write_bytes(b"a = 1\r\n")
    with pytest.raises(RopeError, match="Stale"):
        write_atomic_if_unchanged(str(target), "a = 2\n", b"a = 0\r\n")
    assert target.read_bytes() == b"a = 1\r\n"


# --- apply_text_edits_atomically ----------------------------------------------


@pytest.mark.parametrize(
    "original",
    [
        pytest.param(b"a = 1\r\ny = 2\r\n", id="crlf"),
        pytest.param(b"a = 1\ry = 2\r", id="lone-cr"),
        pytest.param(b"\xef\xbb\xbfa = 1\r\ny = 2\r\n", id="bom-crlf"),
    ],
)
def test_multi_line_insert_does_not_produce_mixed_endings(tmp_path: Path, original: bytes) -> None:
    target = tmp_path / "m.py"
    target.write_bytes(original)
    style = b"\r\n" if b"\r\n" in original else b"\r"
    apply_text_edits_atomically([_edit(target, (1, 0), (1, 0), "z\nw\n")])
    assert target.read_bytes() == original.replace(b"y = 2", b"z" + style + b"w" + style + b"y = 2")


def test_atomic_batch_rollback_restores_exact_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = tmp_path / "a.py", tmp_path / "b.py"
    first.write_bytes(b"a = 1\r\n")
    second.write_bytes(b"b = 1\r\n")
    real = diff_module.write_bytes_atomic_if_unchanged
    calls: list[str] = []

    def flaky(file_path: str, content: bytes, expected: bytes) -> None:
        calls.append(file_path)
        if len(calls) == 2:
            raise RopeError("disk full")
        real(file_path, content, expected)

    monkeypatch.setattr(diff_module, "write_bytes_atomic_if_unchanged", flaky)
    edits = [_edit(first, (0, 4), (0, 5), "10"), _edit(second, (0, 4), (0, 5), "20")]
    with pytest.raises(RopeError, match="all written files were restored"):
        apply_text_edits_atomically(edits)
    assert first.read_bytes() == b"a = 1\r\n"
    assert second.read_bytes() == b"b = 1\r\n"


def test_result_from_text_edits_keeps_crlf(tmp_path: Path) -> None:
    target = tmp_path / "m.py"
    target.write_bytes(b"a = 1\r\nb = 2\r\n")
    result = result_from_text_edits([_edit(target, (0, 4), (0, 5), "10")], "edit", apply=True)
    assert result.applied is True
    assert target.read_bytes() == b"a = 10\r\nb = 2\r\n"


# --- rope ---------------------------------------------------------------------

_SIGNATURE_SOURCE = "def f(a, b):\n    return a + b\n\n\nf(1, 2)\n"
_RENAME = [SignatureOperation(op="rename", index=1, new_name="z")]
_ADD = [SignatureOperation(op="add", index=2, name="c", default="0")]


@pytest.mark.asyncio
@pytest.mark.parametrize("operations", [_RENAME, _ADD], ids=["rename", "add"])
@pytest.mark.parametrize("style", ["\r\n", "\r"])
@pytest.mark.parametrize("final_newline", [True, False], ids=["final-newline", "no-final-newline"])
async def test_change_signature_apply_keeps_line_endings(
    tmp_path: Path, operations: list[SignatureOperation], style: str, final_newline: bool
) -> None:
    source = _SIGNATURE_SOURCE if final_newline else _SIGNATURE_SOURCE.rstrip("\n")
    lf_dir, eol_dir = tmp_path / "lf", tmp_path / "eol"
    lf_dir.mkdir()
    eol_dir.mkdir()
    (lf_dir / "m.py").write_bytes(source.encode())
    (eol_dir / "m.py").write_bytes(source.replace("\n", style).encode())
    await _backend(lf_dir).change_signature(str(lf_dir / "m.py"), 0, 4, operations, apply=True)
    result = await _backend(eol_dir).change_signature(str(eol_dir / "m.py"), 0, 4, operations, apply=True)
    assert result.applied is True
    lf_bytes = (lf_dir / "m.py").read_bytes()
    assert lf_bytes != source.encode()
    assert (eol_dir / "m.py").read_bytes() == lf_bytes.replace(b"\n", style.encode())


@pytest.mark.asyncio
async def test_change_signature_apply_on_a_mixed_file_keeps_unchanged_lines(tmp_path: Path) -> None:
    module = tmp_path / "m.py"
    module.write_bytes(b"def f(a, b):\r\n    return a + b\n\n\nf(1, 2)\r\n")
    await _backend(tmp_path).change_signature(str(module), 0, 4, _RENAME, apply=True)
    assert module.read_bytes() == b"def f(a, z):\r\n    return a + z\n\n\nf(1, 2)\r\n"


@pytest.mark.asyncio
async def test_change_signature_apply_edits_other_files_keeping_their_endings(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_bytes(b"def f(a, b):\r\n    return b\r\n")
    (tmp_path / "other.py").write_bytes(b"from m import f\r\n\r\nf(1, b=2)\r\n")
    await _backend(tmp_path).change_signature(str(tmp_path / "m.py"), 0, 4, _RENAME, apply=True)
    assert (tmp_path / "m.py").read_bytes() == b"def f(a, z):\r\n    return z\r\n"
    assert (tmp_path / "other.py").read_bytes() == b"from m import f\r\n\r\nf(1, 2)\r\n"


def test_apply_edits_with_two_edits_in_one_file_keeps_crlf(tmp_path: Path) -> None:
    target = tmp_path / "m.py"
    target.write_bytes(b"x = 1\r\ny = 2\r\n")
    backend = _backend(tmp_path)
    changed = backend.apply_edits([_edit(target, (0, 4), (0, 5), "10"), _edit(target, (1, 4), (1, 5), "20")])
    assert changed == [str(target), str(target)]
    assert target.read_bytes() == b"x = 10\r\ny = 20\r\n"


def test_apply_edits_rollback_restores_exact_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = [tmp_path / "a.py", tmp_path / "b.py"]
    originals = [b"a = 1\r\n", b"\xef\xbb\xbfb = 1\rc = 2\r"]
    for path, data in zip(paths, originals, strict=True):
        path.write_bytes(data)
    real = rope_backend_module.write_atomic
    calls: list[str] = []

    def flaky(file_path: str, content: str) -> None:
        calls.append(file_path)
        if len(calls) == 2:
            raise RopeError("disk full")
        real(file_path, content)

    monkeypatch.setattr(rope_backend_module, "write_atomic", flaky)
    edits = [_edit(paths[0], (0, 4), (0, 5), "10"), _edit(paths[1], (0, 4), (0, 5), "20")]
    with pytest.raises(RopeError, match="disk full"):
        _backend(tmp_path).apply_edits(edits)
    assert [path.read_bytes() for path in paths] == originals


def test_apply_edits_rollback_continues_past_a_failed_restore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = [tmp_path / "a.py", tmp_path / "b.py", tmp_path / "c.py"]
    for path in paths:
        path.write_bytes(b"x = 1\r\n")
    real_write = rope_backend_module.write_atomic
    real_restore = rope_backend_module.write_bytes_atomic
    writes: list[str] = []

    def fail_third_write(file_path: str, content: str) -> None:
        writes.append(file_path)
        if len(writes) == 3:
            raise RopeError("disk full")
        real_write(file_path, content)

    def fail_first_restore(file_path: str, content: bytes) -> None:
        if file_path == str(paths[0]):
            raise OSError("locked")
        real_restore(file_path, content)

    monkeypatch.setattr(rope_backend_module, "write_atomic", fail_third_write)
    monkeypatch.setattr(rope_backend_module, "write_bytes_atomic", fail_first_restore)
    edits = [_edit(path, (0, 4), (0, 5), "10") for path in paths]
    with pytest.raises(RopeError, match="disk full"):
        _backend(tmp_path).apply_edits(edits)
    assert paths[0].read_bytes() == b"x = 10\r\n"  # its restore failed
    assert paths[1].read_bytes() == b"x = 1\r\n"  # the loop went on
    assert paths[2].read_bytes() == b"x = 1\r\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["\r\n", "\r"])
async def test_split_module_apply_keeps_line_endings(tmp_path: Path, style: str) -> None:
    files = {
        "source.py": "class Beta:\n    pass\n\nclass Alpha:\n    def make(self):\n        return Beta()\n",
        "alpha.py": "# alpha\n",
        "beta.py": "# beta\n",
        "consumer.py": "from source import Alpha, Beta\n\na = Alpha()\nb = Beta()\n",
    }
    lf_dir, eol_dir = tmp_path / "lf", tmp_path / "eol"
    for root, newline in ((lf_dir, "\n"), (eol_dir, style)):
        root.mkdir()
        for name, text in files.items():
            (root / name).write_bytes(text.replace("\n", newline).encode())
    for root in (lf_dir, eol_dir):
        targets = {str(root / "alpha.py"): ["Alpha"], str(root / "beta.py"): ["Beta"]}
        result = await _backend(root).split_module(str(root / "source.py"), targets, apply=True)
        assert result.applied is True
    for name in files:
        lf_bytes = (lf_dir / name).read_bytes()
        assert (eol_dir / name).read_bytes() == lf_bytes.replace(b"\n", style.encode())


# --- other writer families -----------------------------------------------------


async def _run_on_lf_and_eol(tmp_path: Path, source: str, style: str, run: Any) -> tuple[bytes, bytes]:
    """Run *run(path)* on an LF copy and on a *style* copy; return both resulting byte strings."""
    results: list[bytes] = []
    for name, newline in (("lf", "\n"), ("eol", style)):
        path = tmp_path / name / "m.py"
        path.parent.mkdir()
        path.write_bytes(source.replace("\n", newline).encode())
        await run(path)
        results.append(path.read_bytes())
    return results[0], results[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["\r\n", "\r"])
async def test_format_code_apply_keeps_line_endings(tmp_path: Path, style: str) -> None:
    async def run(path: Path) -> None:
        await format_mod.format_code(AsyncMock(), str(path), apply=True)

    lf, eol = await _run_on_lf_and_eol(tmp_path, "x=1\nif x:\n  y   = 2\n", style, run)
    assert lf == b"x = 1\nif x:\n    y = 2\n"
    assert eol == lf.replace(b"\n", style.encode())


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["\r\n", "\r"])
async def test_apply_lint_fixes_keeps_line_endings(tmp_path: Path, style: str) -> None:
    async def run(path: Path) -> None:
        await refactoring.apply_lint_fixes(AsyncMock(), str(path), apply=True)

    lf, eol = await _run_on_lf_and_eol(tmp_path, "import os\nimport sys\n\nprint(sys.argv)\n", style, run)
    assert lf == b"import sys\n\nprint(sys.argv)\n"
    assert eol == lf.replace(b"\n", style.encode())


_DOCSTRING_SOURCE = (
    "def read(path, retries):\n"
    '    """Read a file.\n'
    "\n"
    "    :param str path: Keep this.\n"
    "    :param stale: Remove this.\n"
    '    """\n'
    "    return b''\n"
)


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["\r\n", "\r"])
async def test_docstring_sync_apply_keeps_line_endings(tmp_path: Path, style: str) -> None:
    async def run(path: Path) -> None:
        pyright = AsyncMock()
        pyright.get_diagnostics.return_value = []
        result = await refactoring.docstring_sync(pyright, str(path), 0, 4, apply=True)
        assert result.applied is True

    lf, eol = await _run_on_lf_and_eol(tmp_path, _DOCSTRING_SOURCE, style, run)
    assert b":param retries:" in lf
    assert eol == lf.replace(b"\n", style.encode())


class _Rename(cst.CSTTransformer):
    def leave_Name(self, original_node: cst.Name, updated_node: cst.Name) -> cst.Name:  # noqa: N802
        return updated_node.with_changes(value="renamed") if original_node.value == "old" else updated_node


@pytest.mark.asyncio
@pytest.mark.parametrize("style", ["\r\n", "\r"])
async def test_apply_cst_transformer_keeps_line_endings(tmp_path: Path, style: str) -> None:
    async def run(path: Path) -> None:
        apply_cst_transformer(str(path), _Rename(), apply=True)

    lf, eol = await _run_on_lf_and_eol(tmp_path, "old = 1\n\n\ndef f():\n    return old\n", style, run)
    assert lf == b"renamed = 1\n\n\ndef f():\n    return renamed\n"
    assert eol == lf.replace(b"\n", style.encode())


@pytest.mark.parametrize("style", ["\r\n", "\r"])
def test_apply_cst_transformer_batch_keeps_line_endings(tmp_path: Path, style: str) -> None:
    paths = [tmp_path / "a.py", tmp_path / "b.py"]
    for path in paths:
        path.write_bytes("old = 1\nprint(old)\n".replace("\n", style).encode())
    apply_cst_transformer_batch([str(path) for path in paths], lambda _path: _Rename(), apply=True)
    for path in paths:
        assert path.read_bytes() == "renamed = 1\nprint(renamed)\n".replace("\n", style).encode()
