"""Unit tests for source/type-stub freshness analysis."""

from __future__ import annotations

from pathlib import Path

import pytest

from python_refactor_mcp.errors import ToolInputError
from python_refactor_mcp.tools.analysis.type_stubs import check_type_stub_freshness


def test_reports_signature_and_symbol_drift(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    stub = tmp_path / "service.pyi"
    source.write_text(
        "def load(path: str, *, strict: bool = False) -> str:\n"
        "    return path\n\n"
        "def source_only(value: int) -> int:\n"
        "    return value\n\n"
        "class Service:\n"
        "    def run(self, item: int) -> None:\n"
        "        return None\n",
        encoding="utf-8",
    )
    stub.write_text(
        "def load(path: str) -> str: ...\n\n"
        "def stub_only(value: int) -> int: ...\n\n"
        "class Service:\n"
        "    def run(self, item: int) -> None: ...\n",
        encoding="utf-8",
    )

    result = check_type_stub_freshness(str(source))

    assert result.fresh is False
    assert result.missing_in_stub == ["source_only"]
    assert result.missing_in_source == ["stub_only"]
    assert [item.symbol for item in result.signature_mismatches] == ["load"]
    assert result.signature_mismatches[0].implementation_signature == "(path, *, strict=?)"
    assert result.signature_mismatches[0].stub_signature == "(path)"


def test_overloads_and_protocols_are_conservative_skips(tmp_path: Path) -> None:
    source = tmp_path / "api.py"
    stub = tmp_path / "api.pyi"
    source.write_text(
        "def parse(value: object) -> object:\n"
        "    return value\n\n"
        "class Reader:\n"
        "    def read(self, size: int, timeout: float) -> bytes:\n"
        "        return b''\n",
        encoding="utf-8",
    )
    stub.write_text(
        "from typing import Protocol, overload\n\n"
        "@overload\n"
        "def parse(value: str) -> str: ...\n"
        "@overload\n"
        "def parse(value: bytes) -> bytes: ...\n\n"
        "class Reader(Protocol):\n"
        "    def read(self, size: int) -> bytes: ...\n",
        encoding="utf-8",
    )

    result = check_type_stub_freshness(str(source), str(stub))

    assert result.fresh is True
    assert result.signature_mismatches == []
    assert result.skipped_overloads == ["parse"]
    assert result.skipped_protocols == ["Reader"]


def test_missing_default_stub_is_caller_input_error(tmp_path: Path) -> None:
    source = tmp_path / "service.py"
    source.write_text("def load() -> None:\n    return None\n", encoding="utf-8")

    with pytest.raises(ToolInputError, match=r"^Stub file not found: ") as raised:
        check_type_stub_freshness(str(source))

    message = str(raised.value)
    assert "service.pyi" in message
    assert "parameter: stub_file" in message
    assert "adjacent to source_file" in message


def test_missing_source_is_caller_input_error(tmp_path: Path) -> None:
    with pytest.raises(ToolInputError, match=r"^Source file not found: .*\(parameter: source_file\)$"):
        check_type_stub_freshness(str(tmp_path / "absent.py"))
