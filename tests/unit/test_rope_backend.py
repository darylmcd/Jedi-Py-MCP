"""Unit tests for the rope backend implementation."""

from __future__ import annotations

from pathlib import Path

import pytest
from rope.base.fscommands import FileSystemCommands  # type: ignore[import-untyped]
from rope.contrib.autoimport.sqlite import AutoImport  # type: ignore[import-untyped]

from python_refactor_mcp.backends.rope_backend import RopeBackend
from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import RopeError
from python_refactor_mcp.models import SignatureOperation
from python_refactor_mcp.tools.refactoring.signature_annotations import restore_signature_metadata


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
    fixed = restore_signature_metadata(module.read_text(encoding="utf-8"), edit.new_text, 0, 4, ops)
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
@pytest.mark.parametrize(
    ("import_line", "alias", "new_name", "usage", "expected_import", "expected_usage"),
    [
        (
            "from calc import add as combine",
            "combine",
            "sum_values",
            "result = combine(1, 2)",
            "from calc import add as sum_values",
            "result = sum_values(1, 2)",
        ),
        (
            "import calc as math_ops",
            "math_ops",
            "calculator",
            "result = math_ops.add(1, 2)",
            "import calc as calculator",
            "result = calculator.add(1, 2)",
        ),
    ],
)
async def test_rename_rewrites_import_alias_and_usages_in_preview(
    rope_backend: tuple[RopeBackend, Path],
    import_line: str,
    alias: str,
    new_name: str,
    usage: str,
    expected_import: str,
    expected_usage: str,
) -> None:
    """Rope already performs alias-aware rewrites without a custom CST pass."""
    backend, module = rope_backend
    consumer = module.parent / "consumer.py"
    original = f"{import_line}\n{usage}\n"
    consumer.write_text(original, encoding="utf-8")

    result = await backend.rename(
        str(consumer),
        line=0,
        character=import_line.index(alias),
        new_name=new_name,
        apply=False,
    )

    edit = next(edit for edit in result.edits if Path(edit.file_path).resolve() == consumer.resolve())
    assert expected_import in edit.new_text
    assert expected_usage in edit.new_text
    assert consumer.read_text(encoding="utf-8") == original


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


def _multi_project_fixture(tmp_path: Path) -> tuple[RopeBackend, Path, Path, Path]:
    provider_root = tmp_path / "provider"
    consumer_root = tmp_path / "consumer"
    provider_root.mkdir()
    consumer_root.mkdir()
    provider = provider_root / "library.py"
    consumer = consumer_root / "app.py"
    provider.write_text("class Widget:\n    pass\n", encoding="utf-8")
    consumer.write_text("from library import Widget\n\nitem = Widget()\n", encoding="utf-8")
    backend = RopeBackend(_config(provider_root))
    backend.initialize()
    return backend, provider, consumer, consumer_root


@pytest.mark.asyncio
async def test_multi_project_rename_is_one_undoable_change(tmp_path: Path) -> None:
    backend, provider, consumer, consumer_root = _multi_project_fixture(tmp_path)

    result = await backend.multi_project_rename(
        [str(consumer_root)],
        str(provider),
        line=0,
        character=7,
        new_name="Gadget",
        apply=True,
    )

    assert result.applied is True
    assert "class Gadget" in provider.read_text(encoding="utf-8")
    assert "import Gadget" in consumer.read_text(encoding="utf-8")

    await backend.undo()

    assert provider.read_text(encoding="utf-8") == "class Widget:\n    pass\n"
    assert consumer.read_text(encoding="utf-8") == "from library import Widget\n\nitem = Widget()\n"


@pytest.mark.asyncio
async def test_multi_project_rename_rolls_back_when_later_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, provider, consumer, consumer_root = _multi_project_fixture(tmp_path)
    original_write = FileSystemCommands.write
    failed = False

    def fail_consumer_once(self: FileSystemCommands, path: str, data: bytes) -> None:
        nonlocal failed
        if Path(path).resolve() == consumer.resolve() and not failed:
            failed = True
            raise OSError("simulated consumer write failure")
        original_write(self, path, data)

    monkeypatch.setattr(FileSystemCommands, "write", fail_consumer_once)

    with pytest.raises(RopeError, match="simulated consumer write failure"):
        await backend.multi_project_rename(
            [str(consumer_root)],
            str(provider),
            line=0,
            character=7,
            new_name="Gadget",
            apply=True,
        )

    assert provider.read_text(encoding="utf-8") == "class Widget:\n    pass\n"
    assert consumer.read_text(encoding="utf-8") == "from library import Widget\n\nitem = Widget()\n"


@pytest.mark.asyncio
async def test_autoimport_search_surfaces_backend_failure(
    rope_backend: tuple[RopeBackend, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend, _module = rope_backend

    def fail_search(self: AutoImport, name: str, exact_match: bool = False) -> list[tuple[str, str]]:
        raise RuntimeError("simulated AutoImport search failure")

    monkeypatch.setattr(AutoImport, "search", fail_search)

    with pytest.raises(RopeError, match="simulated AutoImport search failure"):
        await backend.autoimport_search("Widget")


@pytest.mark.asyncio
async def test_autoimport_search_returns_rope_statement_contract(
    rope_backend: tuple[RopeBackend, Path],
) -> None:
    backend, _module = rope_backend

    results = await backend.autoimport_search("add")

    assert ("from calc import add", "add") in results
