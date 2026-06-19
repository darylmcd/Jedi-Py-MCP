"""Unit tests for the SEC022 yaml.load -> yaml.safe_load codemod."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.tools.refactoring.security_autofix import security_autofix


@pytest.mark.asyncio
async def test_preview_rewrites_yaml_load(tmp_path: Path) -> None:
    """Preview emits a rewrite edit but leaves disk untouched."""
    source = "import yaml\n\ndata = yaml.load(stream)\n"
    target = tmp_path / "m.py"
    target.write_text(source, encoding="utf-8")

    result = await security_autofix(AsyncMock(), str(target), apply=False)

    assert result.applied is False
    assert len(result.edits) == 1
    assert "yaml.safe_load(stream)" in result.edits[0].new_text
    assert "Rewrote 1" in result.description
    # Preview — disk untouched.
    assert target.read_text(encoding="utf-8") == source


@pytest.mark.asyncio
async def test_apply_writes_and_refreshes(tmp_path: Path) -> None:
    """``apply=True`` writes the rewrite and notifies Pyright."""
    target = tmp_path / "m.py"
    target.write_text("import yaml\nx = yaml.load(s)\n", encoding="utf-8")

    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await security_autofix(pyright, str(target), apply=True)

    assert result.applied is True
    assert "yaml.safe_load(s)" in target.read_text(encoding="utf-8")
    pyright.notify_file_changed.assert_awaited()


@pytest.mark.asyncio
async def test_skip_explicit_loader_keyword(tmp_path: Path) -> None:
    """A call with an explicit Loader= kwarg is left untouched and counted."""
    source = "import yaml\nx = yaml.load(s, Loader=yaml.FullLoader)\n"
    target = tmp_path / "m.py"
    target.write_text(source, encoding="utf-8")

    result = await security_autofix(AsyncMock(), str(target), apply=False)

    assert result.edits == []
    assert "skipped 1" in result.description
    assert target.read_text(encoding="utf-8") == source


@pytest.mark.asyncio
async def test_skip_explicit_loader_positional(tmp_path: Path) -> None:
    """A second positional arg (the loader) is treated as an explicit loader."""
    target = tmp_path / "m.py"
    target.write_text("import yaml\nx = yaml.load(s, yaml.SafeLoader)\n", encoding="utf-8")

    result = await security_autofix(AsyncMock(), str(target), apply=False)

    assert result.edits == []
    assert "skipped 1" in result.description


@pytest.mark.asyncio
async def test_idempotent_on_safe_load(tmp_path: Path) -> None:
    """Already-safe yaml.safe_load() produces no edits and no skips."""
    target = tmp_path / "m.py"
    target.write_text("import yaml\nx = yaml.safe_load(s)\n", encoding="utf-8")

    result = await security_autofix(AsyncMock(), str(target), apply=False)

    assert result.edits == []
    assert result.description == "No unsafe yaml.load() calls found"


@pytest.mark.asyncio
async def test_alias_not_matched(tmp_path: Path) -> None:
    """Slice 1 scope: aliased imports are not rewritten (documented follow-up)."""
    source = "import yaml as y\nx = y.load(s)\n"
    target = tmp_path / "m.py"
    target.write_text(source, encoding="utf-8")

    result = await security_autofix(AsyncMock(), str(target), apply=False)

    assert result.edits == []
    assert target.read_text(encoding="utf-8") == source


@pytest.mark.asyncio
async def test_skip_double_star_kwargs(tmp_path: Path) -> None:
    """`**kwargs` is unanalyzable (may carry Loader=) -> conservative skip."""
    target = tmp_path / "m.py"
    target.write_text("import yaml\nx = yaml.load(s, **opts)\n", encoding="utf-8")

    result = await security_autofix(AsyncMock(), str(target), apply=False)

    assert result.edits == []
    assert "skipped 1" in result.description


@pytest.mark.asyncio
async def test_multiple_loads_in_one_file(tmp_path: Path) -> None:
    """Every eligible call in a file is rewritten and counted."""
    source = "import yaml\na = yaml.load(x)\nb = yaml.load(y)\n"
    target = tmp_path / "m.py"
    target.write_text(source, encoding="utf-8")

    result = await security_autofix(AsyncMock(), str(target), apply=False)

    assert "Rewrote 2" in result.description
    assert result.edits[0].new_text.count("yaml.safe_load(") == 2


@pytest.mark.asyncio
async def test_preserves_comments_and_whitespace(tmp_path: Path) -> None:
    """Only the attribute is swapped; trivia (comments, spacing) is preserved."""
    source = "import yaml\nx = yaml.load(  s  )  # keep this comment\n"
    target = tmp_path / "m.py"
    target.write_text(source, encoding="utf-8")

    result = await security_autofix(AsyncMock(), str(target), apply=False)

    new_text = result.edits[0].new_text
    assert "yaml.safe_load(  s  )  # keep this comment" in new_text


@pytest.mark.asyncio
async def test_no_targets_reports_clearly() -> None:
    """No file_path and no file_paths -> explicit 'no files' message."""
    result = await security_autofix(AsyncMock(), apply=False)

    assert result.edits == []
    assert result.applied is False
    assert result.description == "No files provided to scan"


@pytest.mark.asyncio
async def test_multiple_files_aggregate(tmp_path: Path) -> None:
    """Counts aggregate across file_paths; mixed rewrite + skip."""
    a = tmp_path / "a.py"
    a.write_text("import yaml\nx = yaml.load(s)\n", encoding="utf-8")
    b = tmp_path / "b.py"
    b.write_text("import yaml\nx = yaml.load(s, Loader=L)\n", encoding="utf-8")

    result = await security_autofix(AsyncMock(), file_paths=[str(a), str(b)], apply=False)

    assert len(result.files_affected) == 1
    assert "Rewrote 1" in result.description
    assert "skipped 1" in result.description
