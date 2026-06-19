"""Unit tests for the change_signature annotation-restoration post-pass."""

from __future__ import annotations

from python_refactor_mcp.models import SignatureOperation
from python_refactor_mcp.tools.refactoring.signature_annotations import restore_param_annotations

# Original annotated definition; the function name `greet` is at line 0, col 4.
ORIGINAL = "def greet(name: str, count: int = 3, verbose: bool = False) -> str:\n    return name\n"


def _restore(new_src: str, ops: list[SignatureOperation]) -> str:
    return restore_param_annotations(ORIGINAL, new_src, 0, 4, ops)


def test_reorder_restores_all_annotations() -> None:
    # rope reorders and strips annotations (names preserved); kept valid (the
    # only no-default param `name` stays first).
    stripped = "def greet(name, verbose=False, count=3) -> str:\n    return name\n"
    out = _restore(stripped, [SignatureOperation(op="reorder", new_order=[0, 2, 1])])
    assert "verbose: bool" in out
    assert "count: int" in out
    assert "name: str" in out


def test_normalize_restores_by_name() -> None:
    stripped = "def greet(name, count=3, verbose=False) -> str:\n    return name\n"
    out = _restore(stripped, [SignatureOperation(op="normalize")])
    assert "name: str" in out and "count: int" in out and "verbose: bool" in out


def test_rename_restores_renamed_param_by_index() -> None:
    # rope renamed `count` -> `n` and dropped annotations; all-rename => index map valid.
    stripped = "def greet(name, n=3, verbose=False) -> str:\n    return name\n"
    out = _restore(stripped, [SignatureOperation(op="rename", index=1, new_name="n")])
    assert "name: str" in out
    assert "n: int" in out  # restored from original position 1 (count: int)
    assert "verbose: bool" in out


def test_add_leaves_new_param_unannotated() -> None:
    stripped = "def greet(name, count=3, verbose=False, extra=None) -> str:\n    return name\n"
    out = _restore(stripped, [SignatureOperation(op="add", index=3, name="extra", default="None")])
    assert "name: str" in out and "count: int" in out
    assert "extra=None" in out  # genuinely new param stays unannotated
    assert "extra:" not in out


def test_mixed_reorder_and_rename_skips_index_restore() -> None:
    # B2: with a position-shuffling op present, a renamed param is NOT guessed
    # by index (which would attach a wrong type). `verbose` renamed -> `v`.
    stripped = "def greet(name, v=False, count=3) -> str:\n    return name\n"
    out = _restore(
        stripped,
        [
            SignatureOperation(op="reorder", new_order=[0, 2, 1]),
            SignatureOperation(op="rename", index=2, new_name="v"),
        ],
    )
    # name-preserving params restored; renamed `v` left unannotated (no wrong type).
    assert "count: int" in out and "name: str" in out
    assert "v: " not in out


def test_no_annotations_is_noop() -> None:
    original = "def f(a, b):\n    return a\n"
    new = "def f(b, a):\n    return a\n"
    assert restore_param_annotations(original, new, 0, 4, [SignatureOperation(op="reorder", new_order=[1, 0])]) == new


def test_already_annotated_is_idempotent() -> None:
    # rope kept annotations -> output unchanged (never overwritten).
    kept = "def greet(count: int = 3, name: str, verbose: bool = False) -> str:\n    return name\n"
    out = _restore(kept, [SignatureOperation(op="reorder", new_order=[1, 0, 2])])
    assert out == kept


def test_return_annotation_restored() -> None:
    stripped = "def greet(name, count=3, verbose=False):\n    return name\n"
    out = _restore(stripped, [SignatureOperation(op="normalize")])
    assert "-> str:" in out


def test_unparseable_new_src_passes_through() -> None:
    broken = "def greet(verbose=False, count=3, name)\n    return name\n"  # missing colon
    out = _restore(broken, [SignatureOperation(op="reorder", new_order=[2, 1, 0])])
    assert out == broken


def test_star_and_kwargs_annotations_restored_by_name() -> None:
    original = "def f(a: int, *args: str, **kw: bool) -> None:\n    return None\n"
    stripped = "def f(a, *args, **kw) -> None:\n    return None\n"
    out = restore_param_annotations(original, stripped, 0, 4, [SignatureOperation(op="normalize")])
    assert "a: int" in out and "*args: str" in out and "**kw: bool" in out
