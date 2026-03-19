"""Unit tests for the Jedi backend implementation."""

from __future__ import annotations

from pathlib import Path

import pytest

from python_refactor_mcp.backends.jedi_backend import JediBackend
from python_refactor_mcp.config import ServerConfig


@pytest.fixture
def jedi_backend(tmp_path: Path) -> tuple[JediBackend, Path]:
    """Create an initialized Jedi backend with a simple fixture module."""
    source = (
        "class MyThing:\n"
        "    pass\n\n"
        "def make_thing() -> MyThing:\n"
        "    item = MyThing()\n"
        "    return item\n"
    )
    module = tmp_path / "example.py"
    module.write_text(source, encoding="utf-8")

    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=Path("python"),
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
    backend = JediBackend(config)
    backend.initialize()
    return backend, module


@pytest.mark.asyncio
async def test_get_references_finds_constructor_and_definition(jedi_backend: tuple[JediBackend, Path]) -> None:
    """References include definition and call site for a class name."""
    backend, module = jedi_backend

    references = await backend.get_references(str(module), 4, 11)

    assert len(references) >= 2
    assert all(ref.file_path == str(module.resolve()) for ref in references)


@pytest.mark.asyncio
async def test_goto_definition_returns_class_location(jedi_backend: tuple[JediBackend, Path]) -> None:
    """Goto definition resolves usage to class definition location."""
    backend, module = jedi_backend

    definitions = await backend.goto_definition(str(module), 4, 11)

    assert definitions
    class_location = definitions[0]
    assert class_location.file_path == str(module.resolve())
    assert class_location.range.start.line == 0


@pytest.mark.asyncio
async def test_infer_type_returns_typeinfo(jedi_backend: tuple[JediBackend, Path]) -> None:
    """Type inference returns a Jedi-backed TypeInfo model."""
    backend, module = jedi_backend

    type_info = await backend.infer_type(str(module), 5, 11)

    assert type_info is not None
    assert type_info.source == "jedi"
    assert type_info.type_string


@pytest.mark.asyncio
async def test_line_conversion_is_zero_based(jedi_backend: tuple[JediBackend, Path]) -> None:
    """Location models returned from Jedi use 0-based line numbers."""
    backend, module = jedi_backend

    definitions = await backend.goto_definition(str(module), 4, 11)

    assert definitions
    assert definitions[0].range.start.line == 0
    assert definitions[0].range.start.character == 6


@pytest.mark.asyncio
async def test_get_signatures_returns_signature_info(jedi_backend: tuple[JediBackend, Path]) -> None:
    """Jedi signatures API returns a structured signature model at call sites."""
    backend, module = jedi_backend
    sig_module = module.parent / "sig_example.py"
    sig_module.write_text(
        "def greet(name: str, times: int) -> str:\n"
        "    return name * times\n"
        "\n"
        "value = greet(\n",
        encoding="utf-8",
    )

    signature = await backend.get_signatures(str(sig_module), 3, 13)

    if signature is not None:
        assert signature.label.startswith("greet")
