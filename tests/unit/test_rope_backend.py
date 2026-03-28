"""Unit tests for the rope backend implementation."""

from __future__ import annotations

from pathlib import Path

import pytest

from python_refactor_mcp.backends.rope_backend import RopeBackend
from python_refactor_mcp.config import ServerConfig


@pytest.fixture
def rope_backend(tmp_path: Path) -> tuple[RopeBackend, Path]:
    """Create initialized rope backend and fixture source file."""
    source = (
        "def add(a: int, b: int) -> int:\n"
        "    value = a + b\n"
        "    return value\n"
    )
    module = tmp_path / "calc.py"
    module.write_text(source, encoding="utf-8")

    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = RopeBackend(config)
    backend.initialize()
    return backend, module


@pytest.mark.asyncio
async def test_rename_returns_text_edits(rope_backend: tuple[RopeBackend, Path]) -> None:
    """Rename returns a non-empty edit set when symbol can be renamed."""
    backend, module = rope_backend

    result = await backend.rename(str(module), 0, 4, "sum_values", apply=False)

    assert not result.applied
    assert result.edits
    assert any(edit.file_path == str(module.resolve()) for edit in result.edits)


@pytest.mark.asyncio
async def test_extract_method_returns_edits(rope_backend: tuple[RopeBackend, Path]) -> None:
    """Extract method creates changes for a selected range."""
    backend, module = rope_backend

    result = await backend.extract_method(
        str(module),
        start_line=1,
        start_character=4,
        end_line=1,
        end_character=17,
        method_name="compute_value",
        apply=False,
    )

    assert result.edits
    assert not result.applied


def test_position_offset_round_trip(rope_backend: tuple[RopeBackend, Path]) -> None:
    """Position and offset conversions round-trip correctly."""
    backend, module = rope_backend

    offset = backend._position_to_offset(str(module), 1, 4)  # pyright: ignore[reportPrivateUsage]
    position = backend._offset_to_position(str(module), offset)  # pyright: ignore[reportPrivateUsage]

    assert position.line == 1
    assert position.character == 4


@pytest.mark.asyncio
async def test_apply_true_writes_file(rope_backend: tuple[RopeBackend, Path]) -> None:
    """apply=True writes changes to disk."""
    backend, module = rope_backend

    result = await backend.rename(str(module), 0, 4, "sum_values", apply=True)

    assert result.applied
    new_content = module.read_text(encoding="utf-8")
    assert "def sum_values" in new_content


@pytest.mark.asyncio
async def test_introduce_parameter_returns_edits(rope_backend: tuple[RopeBackend, Path]) -> None:
    """Introduce parameter returns edits for a callable definition."""
    backend, module = rope_backend

    result = await backend.introduce_parameter(str(module), 0, 4, "c", "0", apply=False)

    assert result.edits
    assert result.applied is False


@pytest.mark.asyncio
async def test_encapsulate_field_returns_edits(tmp_path: Path) -> None:
    """Encapsulate field returns edits for class attribute access."""
    module = tmp_path / "model.py"
    module.write_text(
        "class User:\n"
        "    def __init__(self, name: str):\n"
        "        self.name = name\n"
        "\n"
        "    def get_name(self) -> str:\n"
        "        return self.name\n",
        encoding="utf-8",
    )
    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = RopeBackend(config)
    backend.initialize()

    result = await backend.encapsulate_field(str(module), 2, 13, apply=False)

    assert result.edits
    assert result.applied is False
