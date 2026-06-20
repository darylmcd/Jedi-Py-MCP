"""Unit tests for the atomic multi-tool ``refactor_transaction`` composite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from python_refactor_mcp.backends.rope_backend import RopeBackend
from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import RopeError
from python_refactor_mcp.tools import composite


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


def _rename(module: Path, line: int, character: int, new_name: str) -> dict[str, Any]:
    """Build a rename_symbol transaction step dict."""
    return {
        "tool": "rename_symbol",
        "args": {"file_path": str(module), "line": line, "character": character, "new_name": new_name},
    }


@pytest.mark.asyncio
async def test_two_tool_transaction_commits(tmp_path: Path) -> None:
    """A 2-tool transaction applies both steps atomically and commits to disk.

    Step 2 must preview against the RUNNING (step-1-mutated) source: the second
    rename targets a parameter inside the function step 1 already renamed.
    """
    module = tmp_path / "m.py"
    module.write_text(
        "def add(a, b):\n    return a + b\n\nx = add(1, 2)\n",
        encoding="utf-8",
    )
    backend = _backend(tmp_path)

    result = await composite.refactor_transaction(
        backend,
        steps=[
            _rename(module, 0, 4, "plus"),
            _rename(module, 0, 9, "alpha"),
        ],
    )

    assert result.applied is True
    assert result.rolled_back is False
    assert len(result.steps) == 2
    assert all(step.status == "applied" for step in result.steps)

    content = module.read_text(encoding="utf-8")
    assert "def plus(alpha, b):" in content
    assert "return alpha + b" in content
    assert "x = plus(1, 2)" in content
    assert result.diffs  # diff summary present


@pytest.mark.asyncio
async def test_mid_sequence_failure_rolls_back_cleanly(tmp_path: Path) -> None:
    """A failure on step 2 rolls back step 1 — disk is left byte-identical to the original."""
    module = tmp_path / "m.py"
    original = "def add(a, b):\n    return a + b\n\nx = add(1, 2)\n"
    module.write_text(original, encoding="utf-8")
    backend = _backend(tmp_path)

    with pytest.raises(RopeError):
        await composite.refactor_transaction(
            backend,
            steps=[
                # Step 1 is valid (rename add -> plus).
                _rename(module, 0, 4, "plus"),
                # Step 2 targets the `return` keyword -> rope BadIdentifierError mid-sequence.
                _rename(module, 1, 4, "boom"),
            ],
        )

    # Hard requirement: no partial edits on disk after rollback.
    assert module.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_overlap_detection_aborts_and_rolls_back(tmp_path: Path) -> None:
    """Two steps targeting the same span are rejected; the transaction rolls back."""
    module = tmp_path / "m.py"
    original = "value = 1\nother = value + value\n"
    module.write_text(original, encoding="utf-8")
    backend = _backend(tmp_path)

    with pytest.raises(RopeError, match="overlap"):
        await composite.refactor_transaction(
            backend,
            steps=[
                # Step 1 renames `value` -> `count` at (0, 0).
                _rename(module, 0, 0, "count"),
                # Step 2 targets the SAME definition position again -> overlap.
                _rename(module, 0, 0, "total"),
            ],
        )

    assert module.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_unknown_tool_is_rejected(tmp_path: Path) -> None:
    """An unsupported tool name is rejected with a structured error before any apply."""
    module = tmp_path / "m.py"
    original = "x = 1\n"
    module.write_text(original, encoding="utf-8")
    backend = _backend(tmp_path)

    with pytest.raises(RopeError, match="not supported"):
        await composite.refactor_transaction(
            backend,
            steps=[{"tool": "format_code", "args": {"file_path": str(module)}}],
        )

    assert module.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_empty_steps_rejected(tmp_path: Path) -> None:
    """An empty step list is a structured error, not a silent no-op."""
    backend = _backend(tmp_path)
    with pytest.raises(RopeError, match="at least one step"):
        await composite.refactor_transaction(backend, steps=[])
