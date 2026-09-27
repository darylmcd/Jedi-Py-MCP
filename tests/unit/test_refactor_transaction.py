"""Unit tests for the atomic multi-tool ``refactor_transaction`` composite."""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import TypeAdapter, ValidationError

from python_refactor_mcp.backends.rope_backend import TRANSACTION_TOOLS, RopeBackend
from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import ToolInputError
from python_refactor_mcp.models import TransactionStep
from python_refactor_mcp.tool_params import TransactionSteps
from python_refactor_mcp.tools import composite

_STEPS = TypeAdapter(TransactionSteps)


def _steps(*raw: dict[str, Any]) -> list[TransactionStep]:
    """Validate raw step dicts exactly as the tool's input schema does."""
    return _STEPS.validate_python(list(raw))


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
        steps=_steps(
            _rename(module, 0, 4, "plus"),
            _rename(module, 0, 9, "alpha"),
        ),
    )

    assert result.applied is True
    assert result.rolled_back is False
    assert len(result.steps) == 2
    assert all(step.status == "applied" for step in result.steps)
    assert set(result.files_affected) == {diff.file_path for diff in result.diffs}

    content = module.read_text(encoding="utf-8")
    assert "def plus(alpha, b):" in content
    assert "return alpha + b" in content
    assert "x = plus(1, 2)" in content
    assert result.diffs  # diff summary present


@pytest.mark.asyncio
async def test_mid_sequence_failure_returns_rolled_back_result(tmp_path: Path) -> None:
    """A mid-sequence execution failure RETURNS a rolled-back result; disk is byte-identical.

    Execution failures (a step's refactoring raising mid-sequence) are NOT
    raised. The structured ``TransactionResult`` reports the completed step as
    ``rolled_back``, the failing step as ``failed`` with a populated cause, and
    every later step as ``skipped`` — exercising all four status values.
    """
    module = tmp_path / "m.py"
    original = "def add(a, b):\n    return a + b\n\nx = add(1, 2)\n"
    module.write_text(original, encoding="utf-8")
    backend = _backend(tmp_path)

    result = await composite.refactor_transaction(
        backend,
        steps=_steps(
            # Step 1 is valid (rename add -> plus).
            _rename(module, 0, 4, "plus"),
            # Step 2 targets the `return` keyword -> rope error mid-sequence.
            _rename(module, 1, 4, "boom"),
            # Step 3 is valid in isolation but must be SKIPPED after the abort.
            _rename(module, 0, 9, "alpha"),
        ),
    )

    assert result.applied is False
    assert result.rolled_back is True
    assert len(result.steps) == 3
    # Completed step 1 was applied then reverted.
    assert result.steps[0].status == "rolled_back"
    # Step 2 is the abort point with a non-empty error cause.
    assert result.steps[1].status == "failed"
    assert result.steps[1].error
    # Step 3 never ran.
    assert result.steps[2].status == "skipped"
    assert result.steps[2].error is None
    # No diffs reported because nothing remains on disk.
    assert result.diffs == []
    # Hard requirement: no partial edits on disk after rollback.
    assert module.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_overlap_detection_returns_rolled_back_result(tmp_path: Path) -> None:
    """Two steps targeting the same span -> rolled-back result, not a raise."""
    module = tmp_path / "m.py"
    original = "value = 1\nother = value + value\n"
    module.write_text(original, encoding="utf-8")
    backend = _backend(tmp_path)

    result = await composite.refactor_transaction(
        backend,
        steps=_steps(
            # Step 1 renames `value` -> `count` at (0, 0).
            _rename(module, 0, 0, "count"),
            # Step 2 targets the SAME definition position again -> overlap.
            _rename(module, 0, 0, "total"),
        ),
    )

    assert result.applied is False
    assert result.rolled_back is True
    assert result.steps[0].status == "rolled_back"
    assert result.steps[1].status == "failed"
    assert "overlap" in (result.steps[1].error or "")
    assert module.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_line_insertion_does_not_overlap_later_unchanged_line(tmp_path: Path) -> None:
    """A line-count-changing first step must not mark every shifted line as touched."""
    module = tmp_path / "m.py"
    module.write_text(
        "def calculate():\n"
        "    total = 1 + 2\n"
        "    later = 3\n"
        "    return total + later\n",
        encoding="utf-8",
    )
    backend = _backend(tmp_path)

    result = await composite.refactor_transaction(
        backend,
        steps=_steps(
            {
                "tool": "extract_variable",
                "args": {
                    "file_path": str(module),
                    "start_line": 1,
                    "start_character": 12,
                    "end_line": 1,
                    "end_character": 17,
                    "variable_name": "subtotal",
                },
            },
            _rename(module, 3, 4, "after"),
        ),
    )

    assert result.applied is True
    content = module.read_text(encoding="utf-8")
    assert "subtotal = 1 + 2" in content
    assert "after = 3" in content


def test_step_schema_tags_match_backend_transaction_tools() -> None:
    """The step union's ``tool`` tags are exactly the tools the backend can run."""
    union = get_args(get_args(TransactionStep)[0])
    tags = {tag for member in union for tag in get_args(member.model_fields["tool"].annotation)}
    assert tags == set(TRANSACTION_TOOLS)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Unsupported tool (also in a later step) -> the whole list is rejected up front.
        (
            [_rename(Path("/ws/m.py"), 0, 4, "plus"), {"tool": "format_code", "args": {"file_path": "/ws/m.py"}}],
            r"1[\s\S]*does not match any of the expected tags",
        ),
        (
            [{"tool": "rename_symbol", "args": {"line": 0, "character": 4, "new_name": "x"}}],
            r"file_path[\s\S]*Field required",
        ),
        ([], r"at least 1 item"),
        ([{"args": {"file_path": "/ws/m.py"}}], r"Unable to extract tag using discriminator 'tool'"),
        ([{"tool": "rename_symbol", "args": ["m.py"]}], r"args[\s\S]*valid dictionary"),
        (
            [{**_rename(Path("/ws/m.py"), 0, 4, "x"), "bogus": 1}],
            r"bogus[\s\S]*Extra inputs are not permitted",
        ),
        (
            [
                {
                    "tool": "inline_variable",
                    "args": {"file_path": "/ws/m.py", "line": 0, "character": 0, "new_name": "x"},
                }
            ],
            r"new_name[\s\S]*Extra inputs are not permitted",
        ),
    ],
)
def test_malformed_steps_are_rejected_by_schema_naming_the_field(raw: list[dict[str, Any]], expected: str) -> None:
    """Structural step errors fail input validation, naming the step field, before any edit runs."""
    with pytest.raises(ValidationError, match=expected):
        _STEPS.validate_python(raw)


@pytest.mark.asyncio
async def test_backend_preflight_still_rejects_empty_steps(tmp_path: Path) -> None:
    """Defense in depth: an empty list reaching the composite is an INPUT error, not a no-op."""
    backend = _backend(tmp_path)
    with pytest.raises(ToolInputError, match="at least one step"):
        await composite.refactor_transaction(backend, steps=[])
