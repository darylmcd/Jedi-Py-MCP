"""Unit tests for the rope backend implementation."""

from __future__ import annotations

from pathlib import Path

import pytest

from python_refactor_mcp.backends.rope_backend import RopeBackend
from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import SignatureOperation
from python_refactor_mcp.tools.refactoring.signature_annotations import restore_param_annotations


def _config(tmp_path: Path) -> ServerConfig:
    return ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )


@pytest.mark.asyncio
async def test_change_signature_annotation_restore_end_to_end(tmp_path: Path) -> None:
    """Real rope strips annotations on rename; the post-pass restores them."""
    module = tmp_path / "m.py"
    module.write_text("def greet(name: str, count: int = 3) -> str:\n    return name\n", encoding="utf-8")
    backend = RopeBackend(_config(tmp_path))
    backend.initialize()

    ops = [SignatureOperation(op="rename", index=1, new_name="n")]
    result = await backend.change_signature(str(module), 0, 4, ops, apply=False)
    edit = next(e for e in result.edits if Path(e.file_path).resolve() == module.resolve())

    # Document the defect: rope drops the annotations rename touches.
    assert "count: int" not in edit.new_text
    # The post-pass restores: renamed param by original position, others by name.
    fixed = restore_param_annotations(module.read_text(encoding="utf-8"), edit.new_text, 0, 4, ops)
    assert "name: str" in fixed
    assert "n: int" in fixed
    assert "-> str:" in fixed


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
