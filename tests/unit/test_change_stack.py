"""Regression coverage for the standalone rope change-stack lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest

from python_refactor_mcp.backends.rope_backend import RopeBackend
from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import RopeError


def _backend(tmp_path: Path) -> RopeBackend:
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
    return backend


@pytest.mark.asyncio
async def test_rollback_change_stack_restores_original_bytes(tmp_path: Path) -> None:
    module = tmp_path / "sample.py"
    original = "value = 1\nprint(value)\n"
    module.write_text(original, encoding="utf-8")
    original_bytes = module.read_bytes()
    backend = _backend(tmp_path)

    await backend.begin_change_stack()
    await backend.rename(str(module), 0, 0, "count", apply=True)
    assert module.read_text(encoding="utf-8") != original

    await backend.rollback_change_stack()

    assert module.read_bytes() == original_bytes


@pytest.mark.asyncio
async def test_commit_change_stack_keeps_changes_and_returns_edits(tmp_path: Path) -> None:
    module = tmp_path / "sample.py"
    module.write_text("value = 1\nprint(value)\n", encoding="utf-8")
    backend = _backend(tmp_path)

    await backend.begin_change_stack()
    await backend.rename(str(module), 0, 0, "count", apply=True)
    result = await backend.commit_change_stack()

    assert result.applied is True
    assert result.edits
    assert result.files_affected == [str(module.resolve())]
    assert module.read_text(encoding="utf-8") == "count = 1\nprint(count)\n"


@pytest.mark.asyncio
async def test_begin_change_stack_rejects_nested_stack(tmp_path: Path) -> None:
    backend = _backend(tmp_path)
    await backend.begin_change_stack()

    with pytest.raises(RopeError, match="already active"):
        await backend.begin_change_stack()

    await backend.rollback_change_stack()
