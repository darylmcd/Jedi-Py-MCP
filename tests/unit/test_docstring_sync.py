"""Regression coverage for signature-to-docstring synchronization."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.tools import refactoring


@pytest.mark.asyncio
async def test_docstring_sync_google_preview_preserves_descriptions_and_source(tmp_path: Path) -> None:
    target = tmp_path / "service.py"
    source = (
        "class Service:\n"
        "    def render(self, count: int, *, label: str = 'x') -> str:\n"
        "        \"\"\"Render a label.\n"
        "\n"
        "        Args:\n"
        "            stale: Remove this entry.\n"
        "            count (int): Keep this description.\n"
        "\n"
        "        Returns:\n"
        "            str: The rendered label.\n"
        "        \"\"\"\n"
        "        return label * count\n"
    )
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    result = await refactoring.docstring_sync(pyright, str(target), 1, 8)

    assert result.applied is False
    assert target.read_text(encoding="utf-8") == source
    assert len(result.edits) == 1
    synchronized = result.edits[0].new_text
    assert "            count (int): Keep this description." in synchronized
    assert "            label (str):" in synchronized
    assert "stale" not in synchronized
    assert synchronized.index("count (int)") < synchronized.index("label (str)")
    assert "Returns:" in synchronized
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_docstring_sync_numpy_handles_variadics_and_reorders_entries(tmp_path: Path) -> None:
    target = tmp_path / "maths.py"
    source = (
        "def total(first: int, *values: float, scale: float = 1.0, **options: str) -> float:\n"
        "    \"\"\"Compute a total.\n"
        "\n"
        "    Parameters\n"
        "    ----------\n"
        "    scale : float\n"
        "        Existing scale description.\n"
        "    first : int\n"
        "        Existing first description.\n"
        "    obsolete : str\n"
        "        Remove this entry.\n"
        "\n"
        "    Returns\n"
        "    -------\n"
        "    float\n"
        "    \"\"\"\n"
        "    return first * scale\n"
    )
    target.write_text(source, encoding="utf-8")

    result = await refactoring.docstring_sync(AsyncMock(), str(target), 0, 4)

    synchronized = result.edits[0].new_text
    assert "    first : int\n        Existing first description." in synchronized
    assert "    *values : float" in synchronized
    assert "    scale : float\n        Existing scale description." in synchronized
    assert "    **options : str" in synchronized
    assert "obsolete" not in synchronized
    assert synchronized.index("first : int") < synchronized.index("*values : float")
    assert synchronized.index("*values : float") < synchronized.index("scale : float")
    assert synchronized.index("scale : float") < synchronized.index("**options : str")
    assert "Returns\n    -------" in synchronized


@pytest.mark.asyncio
async def test_docstring_sync_sphinx_apply_refreshes_diagnostics(tmp_path: Path) -> None:
    target = tmp_path / "api.py"
    target.write_text(
        "def fetch(path: str, retries: int = 1) -> bytes:\n"
        "    \"\"\"Fetch a resource.\n"
        "\n"
        "    :param stale: Remove this entry.\n"
        "    :param str path: Keep this description.\n"
        "    :type path: str\n"
        "    :returns: Payload bytes.\n"
        "    \"\"\"\n"
        "    return b''\n",
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await refactoring.docstring_sync(pyright, str(target), 0, 4, apply=True)

    assert result.applied is True
    synchronized = target.read_text(encoding="utf-8")
    assert ":param str path: Keep this description." in synchronized
    assert ":type path: str" in synchronized
    assert ":param retries:" in synchronized
    assert ":type retries: int" in synchronized
    assert "stale" not in synchronized
    assert ":returns: Payload bytes." in synchronized
    pyright.notify_file_changed.assert_awaited_once_with(str(target))
    pyright.get_diagnostics.assert_awaited_once_with(str(target))


@pytest.mark.asyncio
async def test_docstring_sync_explicit_style_adds_first_parameter_section(tmp_path: Path) -> None:
    target = tmp_path / "plain.py"
    target.write_text(
        "def greet(name: str) -> str:\n"
        "    \"\"\"Return a greeting.\"\"\"\n"
        "    return name\n",
        encoding="utf-8",
    )

    result = await refactoring.docstring_sync(
        AsyncMock(),
        str(target),
        0,
        4,
        style="google",
    )

    assert '"""Return a greeting.\n\nArgs:\n    name (str):"""' in result.edits[0].new_text


@pytest.mark.asyncio
async def test_docstring_sync_is_idempotent_after_apply(tmp_path: Path) -> None:
    target = tmp_path / "stable.py"
    target.write_text(
        "def greet(name: str) -> str:\n"
        "    \"\"\"Return a greeting.\n"
        "\n"
        "    Args:\n"
        "        name (str): Existing description.\n"
        "    \"\"\"\n"
        "    return name\n",
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    first = await refactoring.docstring_sync(pyright, str(target), 0, 4, apply=True)
    after_first = target.read_bytes()
    second = await refactoring.docstring_sync(pyright, str(target), 0, 4, apply=True)

    assert first.applied is False
    assert second.applied is False
    assert second.edits == []
    assert target.read_bytes() == after_first
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_docstring_sync_auto_detection_and_unsupported_shapes_fail_closed(tmp_path: Path) -> None:
    target = tmp_path / "plain.py"
    source = (
        "def undocumented(name: str) -> str:\n"
        "    return name\n"
        "\n"
        "def ambiguous(name: str) -> str:\n"
        "    \"\"\"Mixed.\n"
        "\n"
        "    Args:\n"
        "        name: Google.\n"
        "    :param name: Sphinx.\n"
        "    \"\"\"\n"
        "    return name\n"
    )
    target.write_text(source, encoding="utf-8")

    with pytest.raises(BackendError, match="no simple string docstring"):
        await refactoring.docstring_sync(AsyncMock(), str(target), 0, 4)
    with pytest.raises(BackendError, match="Ambiguous docstring styles"):
        await refactoring.docstring_sync(AsyncMock(), str(target), 3, 4)

    assert target.read_text(encoding="utf-8") == source
