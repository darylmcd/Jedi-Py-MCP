"""Unit tests for refactoring tool delegation and apply validation paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.models import Diagnostic, Position, Range, RefactorResult, SignatureOperation, TextEdit
from python_refactor_mcp.tools import refactoring
from tests.helpers import make_diag as _diag, make_edit as _edit


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

    rope.extract_method.assert_awaited_once_with("/repo/a.py", 0, 0, 1, 1, "m", False, False)
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


@pytest.mark.asyncio
async def test_new_refactor_tools_delegate_to_rope() -> None:
    """Ensure newly added rope-backed tools delegate and preserve apply mode."""
    pyright = AsyncMock()
    rope = AsyncMock()
    pyright.prepare_rename.return_value = {
        "range": {
            "start": {"line": 0, "character": 0},
            "end": {"line": 0, "character": 1},
        },
        "placeholder": "f",
    }

    for attr in (
        "change_signature",
        "restructure",
        "use_function",
        "introduce_factory",
        "module_to_package",
        "local_to_field",
        "method_object",
    ):
        getattr(rope, attr).return_value = RefactorResult(edits=[], files_affected=[], description=attr, applied=False)

    operations = [SignatureOperation(op="add", index=0, name="new_arg", default="None")]

    await refactoring.change_signature(pyright, rope, "/repo/a.py", 0, 0, operations, apply=False)
    await refactoring.restructure(pyright, rope, "${x}", "${x}", apply=False)
    await refactoring.use_function(pyright, rope, "/repo/a.py", 0, 0, apply=False)
    await refactoring.introduce_factory(pyright, rope, "/repo/a.py", 0, 0, apply=False)
    await refactoring.module_to_package(pyright, rope, "/repo/a.py", apply=False)
    await refactoring.local_to_field(pyright, rope, "/repo/a.py", 0, 0, apply=False)
    await refactoring.method_object(pyright, rope, "/repo/a.py", 0, 0, apply=False)

    rope.change_signature.assert_awaited_once_with("/repo/a.py", 0, 0, operations, False)
    rope.restructure.assert_awaited_once_with("${x}", "${x}", None, None, None, False)
    rope.use_function.assert_awaited_once_with("/repo/a.py", 0, 0, False)
    rope.introduce_factory.assert_awaited_once_with("/repo/a.py", 0, 0, None, True, False)
    rope.module_to_package.assert_awaited_once_with("/repo/a.py", False)
    rope.local_to_field.assert_awaited_once_with("/repo/a.py", 0, 0, False)
    rope.method_object.assert_awaited_once_with("/repo/a.py", 0, 0, None, False)


@pytest.mark.asyncio
async def test_inline_method_delegates_to_rope() -> None:
    """Ensure inline_method delegates to rope backend."""
    pyright = AsyncMock()
    rope = AsyncMock()
    rope.inline_method.return_value = RefactorResult(
        edits=[_edit("/repo/a.py")], files_affected=["/repo/a.py"], description="inlined", applied=False,
    )
    result = await refactoring.inline_method(pyright, rope, "/repo/a.py", 5, 4, apply=False)
    assert result.applied is False
    rope.inline_method.assert_awaited_once_with("/repo/a.py", 5, 4, False)


@pytest.mark.asyncio
async def test_inline_parameter_delegates_to_rope() -> None:
    """Ensure inline_parameter delegates to rope backend."""
    pyright = AsyncMock()
    rope = AsyncMock()
    rope.inline_parameter.return_value = RefactorResult(
        edits=[_edit("/repo/a.py")], files_affected=["/repo/a.py"], description="inlined param", applied=False,
    )
    result = await refactoring.inline_parameter(pyright, rope, "/repo/a.py", 3, 10, apply=False)
    assert result.applied is False
    rope.inline_parameter.assert_awaited_once_with("/repo/a.py", 3, 10, False)


@pytest.mark.asyncio
async def test_move_method_delegates_to_rope() -> None:
    """Ensure move_method delegates with destination_attr."""
    pyright = AsyncMock()
    rope = AsyncMock()
    rope.move_method.return_value = RefactorResult(
        edits=[_edit("/repo/a.py")], files_affected=["/repo/a.py"], description="moved", applied=False,
    )
    result = await refactoring.move_method(pyright, rope, "/repo/a.py", 2, 4, "other", apply=False)
    assert result.applied is False
    rope.move_method.assert_awaited_once_with("/repo/a.py", 2, 4, "other", False)


@pytest.mark.asyncio
async def test_move_module_delegates_to_rope() -> None:
    """Ensure move_module delegates with source and destination paths."""
    pyright = AsyncMock()
    rope = AsyncMock()
    rope.move_module.return_value = RefactorResult(
        edits=[_edit("/repo/src/mod.py")], files_affected=["/repo/src/mod.py"], description="moved module", applied=False,
    )
    result = await refactoring.move_module(pyright, rope, "/repo/src/mod.py", "/repo/lib/", apply=False)
    assert result.applied is False
    rope.move_module.assert_awaited_once_with("/repo/src/mod.py", "/repo/lib/", False)


@pytest.mark.asyncio
async def test_generate_code_delegates_to_rope() -> None:
    """Ensure generate_code delegates with kind parameter."""
    pyright = AsyncMock()
    rope = AsyncMock()
    rope.generate_code.return_value = RefactorResult(
        edits=[_edit("/repo/a.py")], files_affected=["/repo/a.py"], description="generated", applied=False,
    )
    result = await refactoring.generate_code(pyright, rope, "/repo/a.py", 1, 0, "class", apply=False)
    assert result.applied is False
    rope.generate_code.assert_awaited_once_with("/repo/a.py", 1, 0, "class", False)


@pytest.mark.asyncio
async def test_fix_module_names_delegates_to_rope() -> None:
    """Ensure fix_module_names delegates to rope backend."""
    pyright = AsyncMock()
    rope = AsyncMock()
    rope.fix_module_names.return_value = RefactorResult(
        edits=[], files_affected=[], description="fixed", applied=False,
    )
    result = await refactoring.fix_module_names(pyright, rope, apply=False)
    assert result.applied is False
    rope.fix_module_names.assert_awaited_once_with(False)


@pytest.mark.asyncio
async def test_import_tools_delegate_to_rope() -> None:
    """Ensure all import refactoring tools delegate to rope backend."""
    pyright = AsyncMock()
    rope = AsyncMock()

    for attr in ("expand_star_imports", "relatives_to_absolutes", "froms_to_imports", "handle_long_imports"):
        getattr(rope, attr).return_value = RefactorResult(edits=[], files_affected=[], description=attr, applied=False)

    await refactoring.expand_star_imports(pyright, rope, "/repo/a.py", apply=False)
    await refactoring.relatives_to_absolutes(pyright, rope, "/repo/a.py", apply=False)
    await refactoring.froms_to_imports(pyright, rope, "/repo/a.py", apply=False)
    await refactoring.handle_long_imports(pyright, rope, "/repo/a.py", apply=False)

    rope.expand_star_imports.assert_awaited_once_with("/repo/a.py", False)
    rope.relatives_to_absolutes.assert_awaited_once_with("/repo/a.py", False)
    rope.froms_to_imports.assert_awaited_once_with("/repo/a.py", False)
    rope.handle_long_imports.assert_awaited_once_with("/repo/a.py", False)


@pytest.mark.asyncio
async def test_autoimport_search_returns_suggestions() -> None:
    """Ensure autoimport_search converts rope results to ImportSuggestion models."""
    rope = AsyncMock()
    rope.autoimport_search.return_value = [("Path", "pathlib"), ("PurePath", "pathlib")]

    result = await refactoring.autoimport_search(rope, "Path")

    assert len(result) == 2
    assert result[0].symbol == "Path"
    assert result[0].module == "pathlib"
    assert result[0].import_statement == "from pathlib import Path"
    rope.autoimport_search.assert_awaited_once_with("Path")
