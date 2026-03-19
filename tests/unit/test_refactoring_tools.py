"""Unit tests for refactoring tool delegation and apply validation paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.models import Diagnostic, Position, Range, RefactorResult, TextEdit
from python_refactor_mcp.tools import refactoring


def _edit(path: str) -> TextEdit:
    return TextEdit(
        file_path=path,
        range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
        new_text="x",
    )


def _diag(path: str, line: int) -> Diagnostic:
    return Diagnostic(
        file_path=path,
        range=Range(start=Position(line=line, character=0), end=Position(line=line, character=1)),
        severity="error",
        message=f"e{line}",
        code=None,
    )


@pytest.mark.asyncio
async def test_rename_symbol_delegates_to_rope_no_apply() -> None:
    """Ensure rename delegates arguments and skips diagnostics when not applied."""
    pyright = AsyncMock()
    rope = AsyncMock()
    rope.rename.return_value = RefactorResult(
        edits=[_edit("/repo/a.py")],
        files_affected=["/repo/a.py"],
        description="rename",
        applied=False,
    )

    result = await refactoring.rename_symbol(pyright, rope, "/repo/a.py", 1, 2, "new_name", apply=False)

    assert result.applied is False
    rope.rename.assert_awaited_once_with("/repo/a.py", 1, 2, "new_name", False)
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_symbol_apply_refreshes_diagnostics() -> None:
    """Ensure apply mode notifies Pyright and attaches refreshed diagnostics."""
    pyright = AsyncMock()
    rope = AsyncMock()

    rope.rename.return_value = RefactorResult(
        edits=[_edit("/repo/a.py"), _edit("/repo/b.py")],
        files_affected=["/repo/b.py", "/repo/a.py", "/repo/a.py"],
        description="rename",
        applied=True,
    )
    pyright.get_diagnostics.side_effect = [
        [_diag("/repo/a.py", 2), _diag("/repo/a.py", 1)],
        [_diag("/repo/b.py", 3)],
    ]

    result = await refactoring.rename_symbol(pyright, rope, "/repo/a.py", 1, 2, "new_name", apply=True)

    assert result.diagnostics_after is not None
    assert [item.file_path for item in result.diagnostics_after] == ["/repo/a.py", "/repo/a.py", "/repo/b.py"]
    pyright.notify_file_changed.assert_any_await("/repo/a.py")
    pyright.notify_file_changed.assert_any_await("/repo/b.py")


@pytest.mark.asyncio
async def test_extract_inline_and_move_delegate_correctly() -> None:
    """Ensure all remaining refactor tools delegate to rope backend."""
    pyright = AsyncMock()
    rope = AsyncMock()

    rope.extract_method.return_value = RefactorResult(edits=[], files_affected=[], description="x", applied=False)
    rope.extract_variable.return_value = RefactorResult(edits=[], files_affected=[], description="x", applied=False)
    rope.inline.return_value = RefactorResult(edits=[], files_affected=[], description="x", applied=False)
    rope.move.return_value = RefactorResult(edits=[], files_affected=[], description="x", applied=False)

    await refactoring.extract_method(pyright, rope, "/repo/a.py", 0, 0, 1, 1, "m", apply=False)
    await refactoring.extract_variable(pyright, rope, "/repo/a.py", 0, 0, 1, 1, "v", apply=False)
    await refactoring.inline_variable(pyright, rope, "/repo/a.py", 0, 0, apply=False)
    await refactoring.move_symbol(pyright, rope, "/repo/a.py", "Thing", "/repo/b.py", apply=False)

    rope.extract_method.assert_awaited_once_with("/repo/a.py", 0, 0, 1, 1, "m", False)
    rope.extract_variable.assert_awaited_once_with("/repo/a.py", 0, 0, 1, 1, "v", False)
    rope.inline.assert_awaited_once_with("/repo/a.py", 0, 0, False)
    rope.move.assert_awaited_once_with("/repo/a.py", "Thing", "/repo/b.py", False)


@pytest.mark.asyncio
async def test_apply_code_action_applies_workspace_edits(tmp_path: Path) -> None:
    """Ensure code-action edits can be previewed and applied through the refactoring tool."""
    target = tmp_path / "sample.py"
    target.write_text("value = thing\n", encoding="utf-8")

    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = [
        Diagnostic(
            file_path=str(target),
            range=Range(start=Position(line=0, character=8), end=Position(line=0, character=13)),
            severity="error",
            message="undefined",
            code="reportUndefinedVariable",
        )
    ]
    pyright.get_code_actions.return_value = [
        {
            "title": "Replace with constant",
            "edit": {
                "changes": {
                    target.resolve().as_uri(): [
                        {
                            "range": {
                                "start": {"line": 0, "character": 8},
                                "end": {"line": 0, "character": 13},
                            },
                            "newText": "THING",
                        }
                    ]
                }
            },
        }
    ]

    preview = await refactoring.apply_code_action(pyright, str(target), 0, 9, apply=False)
    assert preview.applied is False
    assert target.read_text(encoding="utf-8") == "value = thing\n"

    pyright.get_diagnostics.side_effect = [
        [
            Diagnostic(
                file_path=str(target),
                range=Range(start=Position(line=0, character=8), end=Position(line=0, character=13)),
                severity="error",
                message="undefined",
                code="reportUndefinedVariable",
            )
        ],
        [],
    ]
    applied = await refactoring.apply_code_action(pyright, str(target), 0, 9, apply=True)
    assert applied.applied is True
    assert "THING" in target.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_organize_imports_selects_source_action(tmp_path: Path) -> None:
    """Ensure organize imports picks the organize-imports code action kind."""
    target = tmp_path / "sample.py"
    target.write_text("import sys\nimport os\n", encoding="utf-8")

    pyright = AsyncMock()
    pyright.get_code_actions.return_value = [
        {
            "title": "Organize Imports",
            "kind": "source.organizeImports",
            "edit": {
                "changes": {
                    target.resolve().as_uri(): [
                        {
                            "range": {
                                "start": {"line": 0, "character": 0},
                                "end": {"line": 2, "character": 0},
                            },
                            "newText": "import os\nimport sys\n",
                        }
                    ]
                }
            },
        }
    ]
    pyright.get_diagnostics.return_value = []

    result = await refactoring.organize_imports(pyright, str(target), apply=True)

    assert result.applied is True
    assert target.read_text(encoding="utf-8") == "import os\nimport sys\n"


@pytest.mark.asyncio
async def test_prepare_rename_passthrough() -> None:
    """Ensure rename preflight delegates directly to Pyright backend."""
    pyright = AsyncMock()
    pyright.prepare_rename.return_value = {
        "range": {
            "start": {"line": 0, "character": 0},
            "end": {"line": 0, "character": 5},
        },
        "placeholder": "value",
    }

    result = await refactoring.prepare_rename(pyright, "/repo/a.py", 0, 0)

    assert result == pyright.prepare_rename.return_value


@pytest.mark.asyncio
async def test_introduce_parameter_and_encapsulate_field_delegate() -> None:
    """Ensure new rope-backed operations delegate and attach diagnostics when applied."""
    pyright = AsyncMock()
    rope = AsyncMock()

    rope.introduce_parameter.return_value = RefactorResult(
        edits=[_edit("/repo/a.py")],
        files_affected=["/repo/a.py"],
        description="introduce",
        applied=False,
    )
    rope.encapsulate_field.return_value = RefactorResult(
        edits=[_edit("/repo/a.py")],
        files_affected=["/repo/a.py"],
        description="encapsulate",
        applied=False,
    )

    intro = await refactoring.introduce_parameter(
        pyright,
        rope,
        "/repo/a.py",
        0,
        0,
        "new_param",
        "1",
        apply=False,
    )
    encapsulated = await refactoring.encapsulate_field(pyright, rope, "/repo/a.py", 0, 0, apply=False)

    assert intro.applied is False
    assert encapsulated.applied is False
    rope.introduce_parameter.assert_awaited_once_with("/repo/a.py", 0, 0, "new_param", "1", False)
    rope.encapsulate_field.assert_awaited_once_with("/repo/a.py", 0, 0, False)
