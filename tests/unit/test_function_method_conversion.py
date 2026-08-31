"""Regression coverage for symmetric function/method conversion tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import Location
from python_refactor_mcp.tools import refactoring
from tests.helpers import make_location


def _location(source: str, file_path: str, line: int, token: str) -> Location:
    return make_location(file_path, line, source.splitlines()[line].index(token))


def _semantic_backends(locations: list[Location]) -> tuple[AsyncMock, AsyncMock]:
    pyright = AsyncMock()
    pyright.get_references.return_value = locations
    jedi = AsyncMock()
    jedi.get_references.return_value = []
    return pyright, jedi


@pytest.mark.asyncio
async def test_convert_function_to_method_rewrites_positional_and_keyword_callers(
    tmp_path: Path,
) -> None:
    target = tmp_path / "ledger.py"
    source = (
        "class Ledger:\n"
        "    pass\n"
        "\n"
        "\n"
        "def total(ledger, amount: int = 1) -> int:\n"
        "    return ledger.value + amount\n"
        "\n"
        "\n"
        "first = total(ledger, 2)\n"
        "second = total(amount=3, ledger=ledger)\n"
    )
    target.write_text(source, encoding="utf-8")
    path = str(target)
    pyright, jedi = _semantic_backends(
        [
            _location(source, path, 4, "total"),
            _location(source, path, 8, "total"),
            _location(source, path, 9, "total"),
        ]
    )

    result = await refactoring.convert_function_to_method(
        pyright,
        jedi,
        path,
        "total",
        "Ledger",
    )

    assert result.applied is False
    assert target.read_text(encoding="utf-8") == source
    assert len(result.edits) == 1
    converted = result.edits[0].new_text
    assert "    def total(ledger, amount: int = 1) -> int:" in converted
    assert "class Ledger:\n    pass" not in converted
    assert "first = ledger.total(2)" in converted
    assert "second = ledger.total(amount=3)" in converted
    assert "\ndef total(" not in converted
    pyright.get_references.assert_awaited_once_with(path, 4, 4, True)
    jedi.get_references.assert_awaited_once_with(path, 4, 4)


@pytest.mark.asyncio
async def test_convert_function_to_method_parenthesizes_expression_receiver(
    tmp_path: Path,
) -> None:
    target = tmp_path / "ledger.py"
    source = (
        "class Ledger:\n"
        "    pass\n"
        "\n"
        "\n"
        "def total(ledger, amount):\n"
        "    return ledger.value + amount\n"
        "\n"
        "\n"
        "result = total(left or right, 2)\n"
    )
    target.write_text(source, encoding="utf-8")
    path = str(target)
    pyright, jedi = _semantic_backends(
        [
            _location(source, path, 4, "total"),
            _location(source, path, 8, "total"),
        ]
    )

    result = await refactoring.convert_function_to_method(
        pyright,
        jedi,
        path,
        "total",
        "Ledger",
    )

    assert "result = (left or right).total(2)" in result.edits[0].new_text


@pytest.mark.asyncio
async def test_convert_method_to_function_rewrites_bound_and_unbound_callers(
    tmp_path: Path,
) -> None:
    target = tmp_path / "ledger.py"
    source = (
        "class Ledger:\n"
        "    def total(self, amount: int) -> int:\n"
        "        return self.value + amount\n"
        "\n"
        "\n"
        "first = ledger.total(2)\n"
        "second = Ledger.total(ledger, 3)\n"
    )
    target.write_text(source, encoding="utf-8")
    path = str(target)
    pyright, jedi = _semantic_backends(
        [
            _location(source, path, 1, "total"),
            _location(source, path, 5, "total"),
            _location(source, path, 6, "total"),
        ]
    )

    result = await refactoring.convert_method_to_function(
        pyright,
        jedi,
        path,
        "Ledger",
        "total",
    )

    converted = result.edits[0].new_text
    assert "class Ledger:\n    pass" in converted
    assert "def total(self, amount: int) -> int:" in converted
    assert "first = total(ledger, 2)" in converted
    assert "second = total(ledger, 3)" in converted


@pytest.mark.asyncio
async def test_convert_method_to_function_apply_writes_and_refreshes_diagnostics(
    tmp_path: Path,
) -> None:
    target = tmp_path / "ledger.py"
    source = "class Ledger:\n    def total(self) -> int:\n        return self.value\n\n\nresult = ledger.total()\n"
    target.write_text(source, encoding="utf-8")
    path = str(target)
    pyright, jedi = _semantic_backends(
        [
            _location(source, path, 1, "total"),
            _location(source, path, 5, "total"),
        ]
    )
    pyright.get_diagnostics.return_value = []

    result = await refactoring.convert_method_to_function(
        pyright,
        jedi,
        path,
        "Ledger",
        "total",
        apply=True,
    )

    assert result.applied is True
    assert "result = total(ledger)" in target.read_text(encoding="utf-8")
    pyright.notify_file_changed.assert_awaited_once_with(path)
    pyright.get_diagnostics.assert_awaited_once_with(path)


@pytest.mark.asyncio
async def test_conversion_rejects_external_references_before_editing(tmp_path: Path) -> None:
    target = tmp_path / "ledger.py"
    external = tmp_path / "caller.py"
    source = "class Ledger:\n    pass\n\n\ndef total(ledger):\n    return ledger.value\n"
    target.write_text(source, encoding="utf-8")
    external.write_text("result = total(ledger)\n", encoding="utf-8")
    path = str(target)
    pyright, jedi = _semantic_backends(
        [
            _location(source, path, 4, "total"),
            make_location(str(external), 0, 9),
        ]
    )

    with pytest.raises(BackendError, match="requires all references"):
        await refactoring.convert_function_to_method(
            pyright,
            jedi,
            path,
            "total",
            "Ledger",
            apply=True,
        )

    assert target.read_text(encoding="utf-8") == source
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_conversion_rejects_non_call_reference_before_editing(tmp_path: Path) -> None:
    target = tmp_path / "ledger.py"
    source = "class Ledger:\n    pass\n\n\ndef total(ledger):\n    return ledger.value\n\n\ncallback = total\n"
    target.write_text(source, encoding="utf-8")
    path = str(target)
    pyright, jedi = _semantic_backends(
        [
            _location(source, path, 4, "total"),
            _location(source, path, 8, "total"),
        ]
    )

    with pytest.raises(BackendError, match="only supports direct call references"):
        await refactoring.convert_function_to_method(
            pyright,
            jedi,
            path,
            "total",
            "Ledger",
        )


@pytest.mark.asyncio
async def test_conversion_requires_reference_declaration_evidence(tmp_path: Path) -> None:
    target = tmp_path / "ledger.py"
    source = "class Ledger:\n    pass\n\n\ndef total(ledger):\n    return ledger.value\n"
    target.write_text(source, encoding="utf-8")
    pyright, jedi = _semantic_backends([])

    with pytest.raises(BackendError, match="did not return the declaration"):
        await refactoring.convert_function_to_method(
            pyright,
            jedi,
            str(target),
            "total",
            "Ledger",
        )


@pytest.mark.asyncio
async def test_conversion_rejects_partial_reference_discovery(tmp_path: Path) -> None:
    target = tmp_path / "ledger.py"
    source = "class Ledger:\n    pass\n\n\ndef total(ledger):\n    return ledger.value\n"
    target.write_text(source, encoding="utf-8")
    path = str(target)
    pyright, jedi = _semantic_backends([_location(source, path, 4, "total")])
    jedi.get_references.side_effect = RuntimeError("provider failed")

    with pytest.raises(BackendError, match="reference discovery was incomplete"):
        await refactoring.convert_function_to_method(
            pyright,
            jedi,
            path,
            "total",
            "Ledger",
        )
