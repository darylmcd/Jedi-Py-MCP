"""Unit tests for structural_replace and the hardened pattern compiler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.tools.search.structural import compile_pattern, structural_replace

_WARN = (
    "m.Call("
    "func=m.Attribute(value=m.Name('logger'), attr=m.Name('warn')), "
    "args=[m.SaveMatchedNode(m.ZeroOrMore(m.Arg()), 'a')])"
)


# ── compile_pattern security (the reason structural_replace can't ship on the old sandbox) ──


def test_compile_pattern_blocks_rce_gadget() -> None:
    """The classic eval-escape gadget must be rejected, not executed."""
    gadget = "().__class__.__bases__[0].__subclasses__()"
    with pytest.raises(ValueError, match="dunder|disallowed|forbidden"):
        compile_pattern(gadget)


def test_compile_pattern_blocks_subscript_and_foreign_names() -> None:
    with pytest.raises(ValueError, match="disallowed|forbidden"):
        compile_pattern("m.Name('x')[0]")
    with pytest.raises(ValueError, match="forbidden name"):
        compile_pattern("open('x')")


def test_compile_pattern_allows_capture_dsl() -> None:
    """Legitimate SaveMatchedNode capture patterns still compile."""
    matcher = compile_pattern(_WARN)
    assert matcher is not None


# ── structural_replace behavior ──


@pytest.mark.asyncio
async def test_preview_rewrites_capture(tmp_path: Path) -> None:
    source = "import logging\nlogger.warn(msg)\n"
    target = tmp_path / "m.py"
    target.write_text(source, encoding="utf-8")

    result = await structural_replace(AsyncMock(), _WARN, "logger.warning($a)", str(target), apply=False)

    assert result.applied is False
    assert len(result.edits) == 1
    assert "logger.warning(msg)" in result.edits[0].new_text
    assert "Rewrote 1" in result.description
    assert target.read_text(encoding="utf-8") == source  # preview: disk untouched


@pytest.mark.asyncio
async def test_apply_writes_and_refreshes(tmp_path: Path) -> None:
    target = tmp_path / "m.py"
    target.write_text("import logging\nlogger.warn(msg)\n", encoding="utf-8")

    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await structural_replace(pyright, _WARN, "logger.warning($a)", str(target), apply=True)

    assert result.applied is True
    assert "logger.warning(msg)" in target.read_text(encoding="utf-8")
    pyright.notify_file_changed.assert_awaited()


@pytest.mark.asyncio
async def test_multi_arg_capture_comma_normalized(tmp_path: Path) -> None:
    """A captured arg sequence must re-render without the trailing-comma bug."""
    target = tmp_path / "m.py"
    target.write_text("import logging\nlogger.warn('x', extra=1)\n", encoding="utf-8")

    result = await structural_replace(AsyncMock(), _WARN, "logger.warning($a)", str(target), apply=False)

    assert "logger.warning('x', extra=1)" in result.edits[0].new_text


@pytest.mark.asyncio
async def test_no_match_returns_empty(tmp_path: Path) -> None:
    target = tmp_path / "m.py"
    target.write_text("import logging\nlogger.info(msg)\n", encoding="utf-8")

    result = await structural_replace(AsyncMock(), _WARN, "logger.warning($a)", str(target), apply=False)

    assert result.edits == []
    assert result.description == "No matches for the pattern"


@pytest.mark.asyncio
async def test_unknown_capture_raises(tmp_path: Path) -> None:
    target = tmp_path / "m.py"
    target.write_text("import logging\nlogger.warn(msg)\n", encoding="utf-8")

    with pytest.raises(BackendError, match="unknown capture"):
        await structural_replace(AsyncMock(), _WARN, "logger.warning($nope)", str(target), apply=False)


@pytest.mark.asyncio
async def test_prefix_safe_capture_substitution(tmp_path: Path) -> None:
    """$a must not match inside $ab — distinct captures render independently."""
    pattern = (
        "m.Call(func=m.Name('pair'), args=["
        "m.SaveMatchedNode(m.Arg(), 'a'), m.SaveMatchedNode(m.Arg(), 'ab')])"
    )
    target = tmp_path / "m.py"
    target.write_text("pair(first, second)\n", encoding="utf-8")

    result = await structural_replace(AsyncMock(), pattern, "pair($ab, $a)", str(target), apply=False)

    assert "pair(second, first)" in result.edits[0].new_text


@pytest.mark.asyncio
async def test_statement_position_match_errors(tmp_path: Path) -> None:
    """A statement-position pattern is rejected cleanly, not via a codegen crash."""
    target = tmp_path / "m.py"
    target.write_text("assert cond\n", encoding="utf-8")

    with pytest.raises(BackendError, match="expression-position"):
        await structural_replace(AsyncMock(), "m.Assert()", "x", str(target), apply=False)


@pytest.mark.asyncio
async def test_no_targets_reports_clearly() -> None:
    result = await structural_replace(AsyncMock(), _WARN, "logger.warning($a)", apply=False)
    assert result.edits == []
    assert result.description == "No files provided to scan"


@pytest.mark.asyncio
async def test_multi_file_aggregate(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    a.write_text("logger.warn(x)\n", encoding="utf-8")
    b = tmp_path / "b.py"
    b.write_text("logger.warn(y)\nlogger.warn(z)\n", encoding="utf-8")

    result = await structural_replace(
        AsyncMock(), _WARN, "logger.warning($a)", file_paths=[str(a), str(b)], apply=False
    )

    assert len(result.files_affected) == 2
    assert "Rewrote 3" in result.description


@pytest.mark.asyncio
async def test_multi_file_apply_is_atomic_on_later_parse_failure(tmp_path: Path) -> None:
    """A malformed later target cannot leave an earlier rewrite applied."""
    first = tmp_path / "first.py"
    broken = tmp_path / "broken.py"
    original = "logger.warn(x)\n"
    first.write_text(original, encoding="utf-8")
    broken.write_text("def oops(:\n", encoding="utf-8")

    with pytest.raises(BackendError, match=r"Failed to parse .*broken\.py"):
        await structural_replace(
            AsyncMock(),
            _WARN,
            "logger.warning($a)",
            file_paths=[str(first), str(broken)],
            apply=True,
        )

    assert first.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_nested_matches_terminate(tmp_path: Path) -> None:
    """Nested matches are each rewritten once; the output never re-matches (no loop)."""
    target = tmp_path / "m.py"
    target.write_text("logger.warn(logger.warn(x))\n", encoding="utf-8")

    result = await structural_replace(AsyncMock(), _WARN, "logger.warning($a)", str(target), apply=False)

    # Both distinct matches fixed; terminates (logger.warning never re-matches logger.warn).
    assert "Rewrote 2" in result.description
    assert result.edits[0].new_text.count("logger.warning(") == 2
