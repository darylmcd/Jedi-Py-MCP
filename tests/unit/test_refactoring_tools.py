"""Unit tests for refactoring tool delegation and apply validation paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.models import Diagnostic, InlayHint, Position, Range, RefactorResult, SignatureOperation
from python_refactor_mcp.tools import refactoring
from tests.helpers import make_diag as _diag
from tests.helpers import make_edit as _edit


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


# ── PR 3-B: Invalid-input / failure-path unit tests ──


@pytest.mark.asyncio
async def test_rename_symbol_rope_raises_propagates() -> None:
    """When rope raises during rename, the error propagates."""
    pyright = AsyncMock()
    rope = AsyncMock()
    pyright.prepare_rename.return_value = object()
    rope.rename.side_effect = ValueError("rope failed")

    with pytest.raises(ValueError, match="rope failed"):
        await refactoring.rename_symbol(pyright, rope, "/repo/a.py", 0, 0, "new_name", apply=False)


def test_change_signature_invalid_op_raises() -> None:
    """When an unsupported operation is passed, Pydantic validation rejects it."""
    with pytest.raises(ValueError, match="Invalid operation"):
        SignatureOperation(op="bad_op")


# ── format_code (ruff-format subprocess wrapper) ──


@pytest.mark.asyncio
async def test_format_code_preview_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Preview mode returns a whole-file edit but leaves disk untouched."""
    from python_refactor_mcp.tools.refactoring import format as format_mod

    target = tmp_path / "m.py"
    original = "x=1\n"
    formatted = "x = 1\n"
    target.write_text(original, encoding="utf-8")

    async def fake_run(file_path: str, content: str) -> str:
        assert content == original
        return formatted

    monkeypatch.setattr(format_mod, "_ruff_format_stdin", fake_run)
    pyright = AsyncMock()

    result = await format_mod.format_code(pyright, str(target), apply=False)

    assert result.applied is False
    assert len(result.edits) == 1
    assert result.edits[0].new_text == formatted
    assert result.files_affected == [str(target)]
    assert target.read_text(encoding="utf-8") == original
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_format_code_apply_writes_and_refreshes_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply mode writes formatted content and notifies Pyright."""
    from python_refactor_mcp.tools.refactoring import format as format_mod

    target = tmp_path / "m.py"
    original = "x=1\n"
    formatted = "x = 1\n"
    target.write_text(original, encoding="utf-8")

    async def fake_run(_fp: str, _content: str) -> str:
        return formatted

    monkeypatch.setattr(format_mod, "_ruff_format_stdin", fake_run)
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await format_mod.format_code(pyright, str(target), apply=True)

    assert result.applied is True
    assert target.read_text(encoding="utf-8") == formatted
    pyright.notify_file_changed.assert_awaited()


@pytest.mark.asyncio
async def test_format_code_noop_when_already_formatted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file that round-trips unchanged yields zero edits."""
    from python_refactor_mcp.tools.refactoring import format as format_mod

    target = tmp_path / "m.py"
    content = "x = 1\n"
    target.write_text(content, encoding="utf-8")

    async def fake_run(_fp: str, c: str) -> str:
        return c

    monkeypatch.setattr(format_mod, "_ruff_format_stdin", fake_run)
    pyright = AsyncMock()

    result = await format_mod.format_code(pyright, str(target), apply=True)

    assert result.applied is False
    assert result.edits == []
    assert result.files_affected == []


@pytest.mark.asyncio
async def test_format_code_batch_mode_filters_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Batch mode includes only files that ruff actually changed."""
    from python_refactor_mcp.tools.refactoring import format as format_mod

    dirty = tmp_path / "dirty.py"
    clean = tmp_path / "clean.py"
    dirty.write_text("a=1\n", encoding="utf-8")
    clean.write_text("b = 2\n", encoding="utf-8")

    async def fake_run(fp: str, c: str) -> str:
        return "a = 1\n" if fp == str(dirty) else c

    monkeypatch.setattr(format_mod, "_ruff_format_stdin", fake_run)
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await format_mod.format_code(
        pyright, file_path=str(dirty), apply=False, file_paths=[str(dirty), str(clean)],
    )

    assert len(result.edits) == 1
    assert result.files_affected == [str(dirty)]


@pytest.mark.asyncio
async def test_format_code_ruff_failure_raises_backend_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-zero ruff exit propagates as BackendError."""
    from python_refactor_mcp.errors import BackendError
    from python_refactor_mcp.tools.refactoring import format as format_mod

    target = tmp_path / "m.py"
    target.write_text("x=1\n", encoding="utf-8")

    async def fake_run(_fp: str, _c: str) -> str:
        raise BackendError("ruff format failed for m.py: parse error")

    monkeypatch.setattr(format_mod, "_ruff_format_stdin", fake_run)
    pyright = AsyncMock()

    with pytest.raises(BackendError, match="ruff format failed"):
        await format_mod.format_code(pyright, str(target), apply=False)


@pytest.mark.asyncio
async def test_format_code_missing_ruff_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When ruff is not on PATH, the wrapper raises a clear BackendError."""
    from python_refactor_mcp.errors import BackendError
    from python_refactor_mcp.tools.refactoring import format as format_mod

    target = tmp_path / "m.py"
    target.write_text("x=1\n", encoding="utf-8")

    monkeypatch.setattr(format_mod.shutil, "which", lambda _: None)
    pyright = AsyncMock()

    with pytest.raises(BackendError, match="ruff executable not found"):
        await format_mod.format_code(pyright, str(target), apply=False)


# ── apply_lint_fixes (ruff check --fix subprocess wrapper) ──


@pytest.mark.asyncio
async def test_apply_lint_fixes_preview_does_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Preview mode returns a whole-file edit but leaves disk untouched."""
    from python_refactor_mcp.tools.refactoring import lint_fix as lint_mod

    target = tmp_path / "m.py"
    original = "import os\nx = 1\n"
    fixed = "x = 1\n"
    target.write_text(original, encoding="utf-8")

    async def fake_run(file_path: str, content: str, unsafe_fixes: bool = False) -> str:
        assert content == original
        assert unsafe_fixes is False
        return fixed

    monkeypatch.setattr(lint_mod, "_ruff_fix_stdin", fake_run)
    pyright = AsyncMock()

    result = await lint_mod.apply_lint_fixes(pyright, str(target), apply=False)

    assert result.applied is False
    assert len(result.edits) == 1
    assert result.edits[0].new_text == fixed
    assert result.files_affected == [str(target)]
    assert target.read_text(encoding="utf-8") == original
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_lint_fixes_apply_writes_and_refreshes_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apply mode writes fixed content and notifies Pyright."""
    from python_refactor_mcp.tools.refactoring import lint_fix as lint_mod

    target = tmp_path / "m.py"
    original = "import os\nx = 1\n"
    fixed = "x = 1\n"
    target.write_text(original, encoding="utf-8")

    async def fake_run(_fp: str, _c: str, unsafe_fixes: bool = False) -> str:
        return fixed

    monkeypatch.setattr(lint_mod, "_ruff_fix_stdin", fake_run)
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await lint_mod.apply_lint_fixes(pyright, str(target), apply=True)

    assert result.applied is True
    assert target.read_text(encoding="utf-8") == fixed
    pyright.notify_file_changed.assert_awaited()


@pytest.mark.asyncio
async def test_apply_lint_fixes_noop_when_no_fixable_issues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file with no fixable lint issues yields zero edits."""
    from python_refactor_mcp.tools.refactoring import lint_fix as lint_mod

    target = tmp_path / "m.py"
    content = "x = 1\n"
    target.write_text(content, encoding="utf-8")

    async def fake_run(_fp: str, c: str, unsafe_fixes: bool = False) -> str:
        return c

    monkeypatch.setattr(lint_mod, "_ruff_fix_stdin", fake_run)
    pyright = AsyncMock()

    result = await lint_mod.apply_lint_fixes(pyright, str(target), apply=True)

    assert result.applied is False
    assert result.edits == []
    assert result.files_affected == []
    assert "No fixable" in result.description


@pytest.mark.asyncio
async def test_apply_lint_fixes_batch_mode_filters_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Batch mode includes only files that ruff actually changed."""
    from python_refactor_mcp.tools.refactoring import lint_fix as lint_mod

    dirty = tmp_path / "dirty.py"
    clean = tmp_path / "clean.py"
    dirty.write_text("import os\nx = 1\n", encoding="utf-8")
    clean.write_text("y = 2\n", encoding="utf-8")

    async def fake_run(fp: str, c: str, unsafe_fixes: bool = False) -> str:
        return "x = 1\n" if fp == str(dirty) else c

    monkeypatch.setattr(lint_mod, "_ruff_fix_stdin", fake_run)
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await lint_mod.apply_lint_fixes(
        pyright, file_path=str(dirty), apply=False, file_paths=[str(dirty), str(clean)],
    )

    assert len(result.edits) == 1
    assert result.files_affected == [str(dirty)]


@pytest.mark.asyncio
async def test_apply_lint_fixes_unsafe_flag_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`unsafe_fixes=True` is forwarded to the subprocess wrapper."""
    from python_refactor_mcp.tools.refactoring import lint_fix as lint_mod

    target = tmp_path / "m.py"
    target.write_text("x = 1\n", encoding="utf-8")
    captured: dict[str, bool] = {}

    async def fake_run(_fp: str, c: str, unsafe_fixes: bool = False) -> str:
        captured["unsafe_fixes"] = unsafe_fixes
        return c

    monkeypatch.setattr(lint_mod, "_ruff_fix_stdin", fake_run)
    pyright = AsyncMock()

    await lint_mod.apply_lint_fixes(pyright, str(target), apply=False, unsafe_fixes=True)

    assert captured["unsafe_fixes"] is True


@pytest.mark.asyncio
async def test_apply_lint_fixes_ruff_failure_raises_backend_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A genuine ruff failure (parse error) propagates as BackendError."""
    from python_refactor_mcp.errors import BackendError
    from python_refactor_mcp.tools.refactoring import lint_fix as lint_mod

    target = tmp_path / "m.py"
    target.write_text("x = 1\n", encoding="utf-8")

    async def fake_run(_fp: str, _c: str, unsafe_fixes: bool = False) -> str:
        raise BackendError("ruff check --fix failed for m.py: parse error")

    monkeypatch.setattr(lint_mod, "_ruff_fix_stdin", fake_run)
    pyright = AsyncMock()

    with pytest.raises(BackendError, match="ruff check --fix failed"):
        await lint_mod.apply_lint_fixes(pyright, str(target), apply=False)


@pytest.mark.asyncio
async def test_apply_lint_fixes_missing_ruff_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """When ruff is not on PATH, the wrapper raises a clear BackendError."""
    from python_refactor_mcp.errors import BackendError
    from python_refactor_mcp.tools.refactoring import lint_fix as lint_mod

    target = tmp_path / "m.py"
    target.write_text("x = 1\n", encoding="utf-8")

    monkeypatch.setattr(lint_mod.shutil, "which", lambda _: None)

    with pytest.raises(BackendError, match="ruff executable not found"):
        await lint_mod._ruff_fix_stdin(str(target), "x = 1\n")


# ── apply_type_annotations (Pyright inlay-hint materializer) ──


def _hint(
    line: int,
    character: int,
    label: str,
    *,
    padding_left: bool = False,
    padding_right: bool = False,
    kind: str | None = "type",
) -> InlayHint:
    """Construct a synthetic Pyright inlay hint at the given source position."""
    return InlayHint(
        position=Position(line=line, character=character),
        label=label,
        kind=kind,
        padding_left=padding_left,
        padding_right=padding_right,
    )


@pytest.mark.asyncio
async def test_apply_type_annotations_preview_does_not_write(tmp_path: Path) -> None:
    """Preview mode emits zero-width insertion edits but leaves disk untouched."""
    source = "def f(x):\n    return x\n"
    target = tmp_path / "m.py"
    target.write_text(source, encoding="utf-8")

    pyright = AsyncMock()
    # ": int" inserted after "x" (line 0, character 7) — zero-width insert.
    pyright.get_inlay_hints.return_value = [_hint(0, 7, ": int")]

    result = await refactoring.apply_type_annotations(pyright, str(target), apply=False)

    assert result.applied is False
    assert len(result.edits) == 1
    edit = result.edits[0]
    assert edit.range.start == edit.range.end  # zero-width insert
    assert edit.new_text == ": int"
    assert result.files_affected == [str(target)]
    # Preview mode — disk untouched.
    assert target.read_text(encoding="utf-8") == source
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_type_annotations_apply_writes_and_refreshes(tmp_path: Path) -> None:
    """``apply=True`` writes the inserted annotation and notifies Pyright."""
    target = tmp_path / "m.py"
    target.write_text("def f(x):\n    return x\n", encoding="utf-8")

    pyright = AsyncMock()
    pyright.get_inlay_hints.return_value = [_hint(0, 7, ": int")]
    pyright.get_diagnostics.return_value = []

    result = await refactoring.apply_type_annotations(pyright, str(target), apply=True)

    assert result.applied is True
    assert target.read_text(encoding="utf-8") == "def f(x: int):\n    return x\n"
    pyright.notify_file_changed.assert_awaited()


@pytest.mark.asyncio
async def test_apply_type_annotations_filters_to_type_kind(tmp_path: Path) -> None:
    """Parameter-name kind hints are dropped; only type hints become edits."""
    target = tmp_path / "m.py"
    target.write_text("def f(x):\n    return x\n", encoding="utf-8")

    pyright = AsyncMock()
    pyright.get_inlay_hints.return_value = [
        _hint(0, 7, ": int", kind="type"),
        _hint(1, 11, "x=", kind="parameter"),  # parameter-name hint at a call site
    ]

    result = await refactoring.apply_type_annotations(pyright, str(target), apply=False)

    assert len(result.edits) == 1
    assert result.edits[0].new_text == ": int"


@pytest.mark.asyncio
async def test_apply_type_annotations_honors_padding_flags(tmp_path: Path) -> None:
    """``padding_left`` / ``padding_right`` flags add surrounding whitespace."""
    target = tmp_path / "m.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")

    pyright = AsyncMock()
    # Return-type hint after `)` on `def f()`. Pyright emits `-> int` and may
    # request leading + trailing spaces depending on tokenization.
    pyright.get_inlay_hints.return_value = [
        _hint(0, 7, "-> int", padding_left=True, padding_right=True),
    ]

    result = await refactoring.apply_type_annotations(pyright, str(target), apply=False)

    assert len(result.edits) == 1
    assert result.edits[0].new_text == " -> int "


@pytest.mark.asyncio
async def test_apply_type_annotations_no_hints_returns_empty(tmp_path: Path) -> None:
    """A file with no type-kind hints yields no edits and a clear description."""
    target = tmp_path / "m.py"
    target.write_text("x = 1\n", encoding="utf-8")

    pyright = AsyncMock()
    pyright.get_inlay_hints.return_value = []

    result = await refactoring.apply_type_annotations(pyright, str(target), apply=True)

    assert result.applied is False
    assert result.edits == []
    assert result.files_affected == []
    assert "No inferable" in result.description


@pytest.mark.asyncio
async def test_apply_type_annotations_batch_mode_aggregates(tmp_path: Path) -> None:
    """Batch mode walks every supplied path and aggregates per-file edits."""
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("def f(x):\n    return x\n", encoding="utf-8")
    b.write_text("y = 1\n", encoding="utf-8")  # no hints

    pyright = AsyncMock()

    async def fake_hints(file_path: str, _sl: int, _sc: int, _el: int, _ec: int):  # noqa: ANN202
        if file_path == str(a):
            return [_hint(0, 7, ": int")]
        return []

    pyright.get_inlay_hints.side_effect = fake_hints

    result = await refactoring.apply_type_annotations(
        pyright, file_path=str(a), apply=False, file_paths=[str(a), str(b)],
    )

    assert len(result.edits) == 1
    assert result.files_affected == [str(a)]


@pytest.mark.asyncio
async def test_apply_type_annotations_missing_file_raises(tmp_path: Path) -> None:
    """Reading a missing file surfaces as a ``BackendError`` with read context."""
    from python_refactor_mcp.errors import BackendError

    missing = tmp_path / "nope.py"
    pyright = AsyncMock()

    with pytest.raises(BackendError, match="Cannot read file for type annotation"):
        await refactoring.apply_type_annotations(pyright, str(missing), apply=False)
