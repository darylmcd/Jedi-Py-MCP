"""Regression tests for conservative circular-import remediation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.tools import refactoring
from tests.helpers import make_config


def _write_module(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_fix_circular_imports_previews_annotation_only_edge(tmp_path: Path) -> None:
    first = _write_module(
        tmp_path / "first.py",
        "from second import Item\n\ndef identity(value: Item) -> Item:\n    return value\n",
    )
    _write_module(
        tmp_path / "second.py",
        "from first import identity\n\nclass Item:\n    pass\n",
    )

    result = await refactoring.fix_circular_imports(
        AsyncMock(),
        make_config(tmp_path),
        file_path=str(first),
    )

    assert result.applied is False
    assert result.files_affected == [str(first.resolve())]
    assert len(result.edits) == 1
    rewritten = result.edits[0].new_text
    assert "from typing import TYPE_CHECKING" in rewritten
    assert "if TYPE_CHECKING:\n    from second import Item" in rewritten
    assert "def identity(value: 'Item') -> 'Item':" in rewritten
    assert first.read_text(encoding="utf-8").startswith("from second import Item")


@pytest.mark.asyncio
async def test_fix_circular_imports_leaves_mixed_runtime_edge_unchanged(tmp_path: Path) -> None:
    first = _write_module(
        tmp_path / "first.py",
        "from second import Item\n\ndef build(value: Item) -> Item:\n    return Item()\n",
    )
    _write_module(tmp_path / "second.py", "import first\n\nclass Item:\n    pass\n")

    result = await refactoring.fix_circular_imports(
        AsyncMock(),
        make_config(tmp_path),
        file_path=str(first),
    )

    assert result.edits == []
    assert result.files_affected == []
    assert "mixed and runtime imports were left unchanged" in result.description


@pytest.mark.asyncio
async def test_fix_circular_imports_apply_refreshes_diagnostics(tmp_path: Path) -> None:
    first = _write_module(
        tmp_path / "first.py",
        "from second import Item\n\ndef identity(value: Item) -> Item:\n    return value\n",
    )
    _write_module(tmp_path / "second.py", "import first\n\nclass Item:\n    pass\n")
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await refactoring.fix_circular_imports(
        pyright,
        make_config(tmp_path),
        file_path=str(first),
        apply=True,
    )

    assert result.applied is True
    assert "if TYPE_CHECKING:" in first.read_text(encoding="utf-8")
    pyright.notify_file_changed.assert_awaited_once_with(str(first.resolve()))
    pyright.get_diagnostics.assert_awaited_once_with(str(first.resolve()))


@pytest.mark.asyncio
async def test_fix_circular_imports_preserves_postponed_annotations(tmp_path: Path) -> None:
    first = _write_module(
        tmp_path / "first.py",
        "from __future__ import annotations\n\n"
        "from second import Item\n\n"
        "def identity(value: Item) -> Item:\n"
        "    return value\n",
    )
    _write_module(tmp_path / "second.py", "import first\n\nclass Item:\n    pass\n")

    result = await refactoring.fix_circular_imports(
        AsyncMock(),
        make_config(tmp_path),
        file_path=str(first),
    )

    rewritten = result.edits[0].new_text
    assert "def identity(value: Item) -> Item:" in rewritten
    assert "value: 'Item'" not in rewritten


@pytest.mark.asyncio
async def test_fix_circular_imports_rejects_type_checking_name_collision(tmp_path: Path) -> None:
    first = _write_module(
        tmp_path / "first.py",
        "from second import Item\nTYPE_CHECKING = True\n\ndef identity(value: Item) -> Item:\n    return value\n",
    )
    _write_module(tmp_path / "second.py", "import first\n\nclass Item:\n    pass\n")

    with pytest.raises(BackendError, match="TYPE_CHECKING guard"):
        await refactoring.fix_circular_imports(
            AsyncMock(),
            make_config(tmp_path),
            file_path=str(first),
        )
