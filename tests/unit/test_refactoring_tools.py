"""Unit tests for refactoring tool delegation and apply validation paths."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock

import libcst as cst
import pytest

from python_refactor_mcp.errors import BackendError, RopeError
from python_refactor_mcp.models import (
    Diagnostic,
    InlayHint,
    Position,
    Range,
    RefactorResult,
    SignatureOperation,
    TextEdit,
    TypeInfo,
)
from python_refactor_mcp.tools import refactoring
from python_refactor_mcp.tools.refactoring import (
    dataclass_conversion,
    pydantic_conversion,
    typed_dict_conversion,
)
from python_refactor_mcp.tools.refactoring.helpers import result_from_text_edits
from python_refactor_mcp.util import cst_imports
from python_refactor_mcp.util.cst_apply import (
    CstSourceSnapshot,
)
from python_refactor_mcp.util.cst_apply import (
    apply_cst_transformer as apply_cst_transformer_direct,
)
from tests.helpers import make_diag as _diag
from tests.helpers import make_edit as _edit


def test_result_from_text_edits_preflights_multi_file_batch(tmp_path: Path) -> None:
    """A later invalid rope/LSP edit leaves every target unchanged."""
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("a = 1\n", encoding="utf-8")
    second.write_text("b = 2\n", encoding="utf-8")
    edits = [
        TextEdit(
            file_path=str(first),
            range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
            new_text="renamed",
        ),
        TextEdit(
            file_path=str(second),
            range=Range(start=Position(line=99, character=0), end=Position(line=99, character=1)),
            new_text="invalid",
        ),
    ]

    with pytest.raises(RopeError, match="Line out of range"):
        result_from_text_edits(edits, "multi-file", apply=True)

    assert first.read_text(encoding="utf-8") == "a = 1\n"
    assert second.read_text(encoding="utf-8") == "b = 2\n"


@pytest.mark.asyncio
async def test_rename_symbol_delegates_to_rope_no_apply(tmp_path: Path) -> None:
    """Ensure rename delegates arguments and skips diagnostics when not applied."""
    module = tmp_path / "a.py"
    module.write_text("value = 1\n", encoding="utf-8")
    module_path = str(module)
    pyright = AsyncMock()
    rope = AsyncMock()
    rope.rename.return_value = RefactorResult(
        edits=[_edit(module_path)],
        files_affected=[module_path],
        description="rename",
        applied=False,
    )

    result = await refactoring.rename_symbol(pyright, rope, module_path, 0, 0, "new_name", apply=False)

    assert result.applied is False
    rope.rename.assert_awaited_once_with(module_path, 0, 0, "new_name", False)
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_symbol_read_failure_is_backend_error(tmp_path: Path) -> None:
    """Filesystem diagnostics stay behind the backend-error boundary."""
    missing = tmp_path / "private" / "missing.py"

    with pytest.raises(BackendError, match="Rename preflight could not read"):
        await refactoring.rename_symbol(
            AsyncMock(),
            AsyncMock(),
            str(missing),
            0,
            0,
            "renamed",
        )


@pytest.mark.asyncio
async def test_rename_symbol_apply_refreshes_diagnostics(tmp_path: Path) -> None:
    """Ensure apply mode notifies Pyright and attaches refreshed diagnostics."""
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("value = 1\n", encoding="utf-8")
    second.write_text("other = 2\n", encoding="utf-8")
    first_path = str(first)
    second_path = str(second)
    pyright = AsyncMock()
    rope = AsyncMock()

    rope.rename.return_value = RefactorResult(
        edits=[_edit(first_path), _edit(second_path)],
        files_affected=[second_path, first_path, first_path],
        description="rename",
        applied=True,
    )
    pyright.get_diagnostics.side_effect = [
        [_diag(first_path, 2), _diag(first_path, 1)],
        [_diag(second_path, 3)],
    ]

    result = await refactoring.rename_symbol(pyright, rope, first_path, 0, 0, "new_name", apply=True)

    assert result.diagnostics_after is not None
    assert [item.file_path for item in result.diagnostics_after] == [first_path, first_path, second_path]
    pyright.notify_file_changed.assert_any_await(first_path)
    pyright.notify_file_changed.assert_any_await(second_path)


@pytest.mark.asyncio
async def test_import_alias_rename_rejects_same_scope_collision(tmp_path: Path) -> None:
    """An alias rename cannot silently merge with an existing local binding."""
    module = tmp_path / "consumer.py"
    source = (
        "from provider import Widget as Alias\n"
        "Renamed = object()\n"
        "instance = Alias()\n"
    )
    module.write_text(source, encoding="utf-8")

    pyright = AsyncMock()
    pyright.prepare_rename.return_value = object()
    rope = AsyncMock()

    with pytest.raises(ValueError, match="target name is already bound in the same scope"):
        await refactoring.rename_symbol(
            pyright,
            rope,
            str(module),
            line=0,
            character=source.splitlines()[0].index("Alias"),
            new_name="Renamed",
        )
    rope.rename.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_alias_rename_allows_available_name(tmp_path: Path) -> None:
    """An unbound target name continues to Rope's alias-aware rename path."""
    module = tmp_path / "consumer.py"
    source = "import provider as alias\ninstance = alias.Widget()\n"
    module.write_text(source, encoding="utf-8")
    alias_character = source.splitlines()[0].index("alias")

    pyright = AsyncMock()
    pyright.prepare_rename.return_value = object()
    rope = AsyncMock()
    rope.rename.return_value = RefactorResult(
        edits=[],
        files_affected=[],
        description="rename",
        applied=False,
    )

    await refactoring.rename_symbol(
        pyright,
        rope,
        str(module),
        line=0,
        character=alias_character,
        new_name="available",
    )

    rope.rename.assert_awaited_once_with(str(module), 0, alias_character, "available", False)


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
    rope.autoimport_search.return_value = [
        ("from pathlib import Path", "Path"),
        ("from pathlib import PurePath", "PurePath"),
    ]

    result = await refactoring.autoimport_search(rope, "Path")

    assert len(result) == 2
    assert result[0].symbol == "Path"
    assert result[0].module == "pathlib"
    assert result[0].import_statement == "from pathlib import Path"
    rope.autoimport_search.assert_awaited_once_with("Path")


# ── PR 3-B: Invalid-input / failure-path unit tests ──


@pytest.mark.asyncio
async def test_rename_symbol_rope_raises_propagates(tmp_path: Path) -> None:
    """When rope raises during rename, the error propagates."""
    module = tmp_path / "a.py"
    module.write_text("value = 1\n", encoding="utf-8")
    pyright = AsyncMock()
    rope = AsyncMock()
    pyright.prepare_rename.return_value = object()
    rope.rename.side_effect = ValueError("rope failed")

    with pytest.raises(ValueError, match="rope failed"):
        await refactoring.rename_symbol(pyright, rope, str(module), 0, 0, "new_name", apply=False)


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


# ── convert_to_dataclass (conservative LibCST conversion) ──


@pytest.mark.parametrize(
    (
        "source",
        "after_import_block",
        "expected_index",
        "preferred",
        "fallback",
        "expected_binding",
    ),
    [
        (
            '"""Module docs."""\nfrom __future__ import annotations\nimport typing as t\nclass User: pass\n',
            False,
            2,
            "TypedDict",
            "_mcp_TypedDict",
            "TypedDict",
        ),
        (
            "if enabled:\n    dataclass = object()\n_mcp_dataclass = object()\n",
            False,
            0,
            "dataclass",
            "_mcp_dataclass",
            "_mcp_dataclass_2",
        ),
        (
            "from pydantic import BaseModel as model_base\nmodel_base = object()\n",
            True,
            1,
            "model_base",
            "_mcp_model_base",
            "_mcp_model_base",
        ),
    ],
)
def test_cst_import_planning_handles_imports_collisions_and_rebindings(
    source: str,
    after_import_block: bool,
    expected_index: int,
    preferred: str,
    fallback: str,
    expected_binding: str,
) -> None:
    module = cst.parse_module(source)
    bindings = cst_imports.top_level_bindings(module)

    assert cst_imports.import_insertion_index(
        module.body,
        after_import_block=after_import_block,
    ) == expected_index
    assert cst_imports.reserve_unique_binding(bindings, preferred, fallback) == expected_binding


@pytest.mark.asyncio
async def test_convert_to_dataclass_does_not_reuse_late_import(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    source = (
        '"""Models."""\n'
        "from __future__ import annotations\n"
        "\n"
        "dataclass = object()\n"
        "_mcp_dataclass = object()\n"
        "\n"
        "class User:\n"
        "    def __init__(self, name: str):\n"
        "        self.name = name\n"
        "\n"
        "from dataclasses import dataclass as late_dataclass\n"
    )
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    result = await refactoring.convert_to_dataclass(pyright, str(target), "User")

    converted = result.edits[0].new_text
    generated_import = "from dataclasses import dataclass as _mcp_dataclass_2"
    assert converted.index('"""Models."""') < converted.index("from __future__ import annotations")
    assert converted.index("from __future__ import annotations") < converted.index(generated_import)
    assert converted.index(generated_import) < converted.index("class User:")
    assert "@_mcp_dataclass_2\nclass User:" in converted
    assert "from dataclasses import dataclass as late_dataclass" in converted
    compile(converted, str(target), "exec")


@pytest.mark.asyncio
async def test_convert_to_dataclass_typed_preview_preserves_source(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    source = (
        "class User:\n"
        "    def __init__(self, name: str, enabled: bool = True):\n"
        "        self.name = name\n"
        "        self.enabled = enabled\n"
        "\n"
        "    def label(self) -> str:\n"
        "        return self.name\n"
    )
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    result = await refactoring.convert_to_dataclass(pyright, str(target), "User")

    assert result.applied is False
    assert target.read_text(encoding="utf-8") == source
    assert len(result.edits) == 1
    converted = result.edits[0].new_text
    assert "from dataclasses import dataclass" in converted
    assert "@dataclass\nclass User:" in converted
    assert "    name: str\n" in converted
    assert "    enabled: bool = True\n" in converted
    assert "def __init__" not in converted
    assert "    def label(self) -> str:" in converted
    pyright.get_hover.assert_not_awaited()
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_convert_to_dataclass_uses_pyright_for_untyped_field(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    target.write_text(
        "class User:\n"
        "    def __init__(self, name):\n"
        "        self.name = name\n",
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_hover.return_value = TypeInfo(
        expression=f"{target}:1:23",
        type_string="(parameter) name: builtins.str",
        source="pyright",
    )

    result = await refactoring.convert_to_dataclass(pyright, str(target), "User")

    assert "    name: str\n" in result.edits[0].new_text
    pyright.get_hover.assert_awaited_once_with(str(target), 1, 23)


@pytest.mark.asyncio
async def test_convert_to_dataclass_apply_writes_and_refreshes(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    target.write_text(
        "class User:\n"
        "    def __init__(self, name: str):\n"
        "        self.name = name\n",
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await refactoring.convert_to_dataclass(pyright, str(target), "User", apply=True)

    assert result.applied is True
    assert "@dataclass" in target.read_text(encoding="utf-8")
    pyright.notify_file_changed.assert_awaited_once_with(str(target))
    pyright.get_diagnostics.assert_awaited_once_with(str(target))


@pytest.mark.asyncio
async def test_convert_to_dataclass_ignores_same_named_nested_class(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    target.write_text(
        "class Container:\n"
        "    class User:\n"
        "        def __init__(self, nested: str):\n"
        "            self.nested = nested\n"
        "\n"
        "class User:\n"
        "    def __init__(self, name: str):\n"
        "        self.name = name\n",
        encoding="utf-8",
    )
    pyright = AsyncMock()

    result = await refactoring.convert_to_dataclass(pyright, str(target), "User")

    converted = result.edits[0].new_text
    assert converted.count("@dataclass") == 1
    assert converted.count("def __init__") == 1
    assert "            self.nested = nested" in converted


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,error",
    [
        (
            "class User:\n"
            "    def __init__(self, name: str):\n"
            "        self.name = name.strip()\n",
            "only supports ordered direct",
        ),
        (
            "class User:\n"
            "    def __init__(self, names: list[str] = []):\n"
            "        self.names = names\n",
            "Mutable default",
        ),
    ],
)
async def test_convert_to_dataclass_rejects_unsafe_constructor_shapes(
    tmp_path: Path,
    source: str,
    error: str,
) -> None:
    target = tmp_path / "models.py"
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    with pytest.raises(BackendError, match=error):
        await refactoring.convert_to_dataclass(pyright, str(target), "User")

    assert target.read_text(encoding="utf-8") == source
    pyright.get_hover.assert_not_awaited()


# ── convert_to_pydantic (bounded Pydantic v2 conversion) ──


@pytest.mark.asyncio
async def test_convert_to_pydantic_preview_preserves_validation_and_call_shape(
    tmp_path: Path,
) -> None:
    target = tmp_path / "models.py"
    source = (
        "class User:\n"
        "    def __init__(self, *, name: str, enabled: bool = True) -> None:\n"
        "        if not name.strip():\n"
        "            raise ValueError(\"name is required\")\n"
        "        self.name = name\n"
        "        self.enabled = enabled\n"
        "\n"
        "    def label(self) -> str:\n"
        "        return self.name\n"
    )
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    result = await refactoring.convert_to_pydantic(pyright, str(target), "User")

    assert result.applied is False
    assert target.read_text(encoding="utf-8") == source
    assert len(result.edits) == 1
    converted = result.edits[0].new_text
    assert "from pydantic import BaseModel, ConfigDict, field_validator" in converted
    assert "class User(BaseModel):" in converted
    assert 'model_config = ConfigDict(extra="forbid")' in converted
    assert "    name: str\n" in converted
    assert "    enabled: bool = True\n" in converted
    assert "@field_validator('name')" in converted
    assert "if not value.strip():" in converted
    assert "def __init__" not in converted
    assert "    def label(self) -> str:" in converted
    pyright.notify_file_changed.assert_not_awaited()

    namespace: dict[str, object] = {}
    exec(compile(converted, str(target), "exec"), namespace)  # noqa: S102
    user_type = namespace["User"]
    valid = user_type(name="Ada")  # type: ignore[operator]
    assert valid.label() == "Ada"
    with pytest.raises(ValueError, match="name is required"):
        user_type(name=" ")  # type: ignore[operator]
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        user_type(name="Ada", unexpected=True)  # type: ignore[operator]
    with pytest.raises(TypeError):
        user_type("Ada")  # type: ignore[operator]


@pytest.mark.asyncio
async def test_convert_to_pydantic_apply_writes_and_refreshes(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    target.write_text(
        "class User:\n"
        "    def __init__(self, *, name: str) -> None:\n"
        "        if not name:\n"
        "            raise ValueError(\"name is required\")\n"
        "        self.name = name\n",
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await refactoring.convert_to_pydantic(
        pyright,
        str(target),
        "User",
        apply=True,
    )

    assert result.applied is True
    assert "class User(BaseModel):" in target.read_text(encoding="utf-8")
    pyright.notify_file_changed.assert_awaited_once_with(str(target))
    pyright.get_diagnostics.assert_awaited_once_with(str(target))


@pytest.mark.asyncio
async def test_convert_to_pydantic_does_not_reuse_late_imports(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    source = (
        "class User:\n"
        "    def __init__(self, *, name: str) -> None:\n"
        "        if not name:\n"
        "            raise ValueError(\"name is required\")\n"
        "        self.name = name\n"
        "\n"
        "from pydantic import BaseModel, ConfigDict, field_validator\n"
    )
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    result = await refactoring.convert_to_pydantic(pyright, str(target), "User")

    converted = result.edits[0].new_text
    generated_import = (
        "from pydantic import BaseModel as _mcp_pydantic_basemodel, "
        "ConfigDict as _mcp_pydantic_configdict, "
        "field_validator as _mcp_pydantic_field_validator"
    )
    assert generated_import in converted
    assert converted.index(generated_import) < converted.index("class User(")
    assert "class User(_mcp_pydantic_basemodel):" in converted

    namespace: dict[str, object] = {}
    exec(compile(converted, str(target), "exec"), namespace)  # noqa: S102
    user_type = namespace["User"]
    assert user_type(name="Ada").name == "Ada"  # type: ignore[operator]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,error",
    [
        (
            "from pydantic import *\n"
            "class User:\n"
            "    def __init__(self, *, name: str) -> None:\n"
            "        if not name:\n"
            "            raise ValueError(\"name\")\n"
            "        self.name = name\n",
            "wildcard Pydantic imports",
        ),
        (
            "class User:\n"
            "    def __init__(self, name: str) -> None:\n"
            "        if not name:\n"
            "            raise ValueError(\"name\")\n"
            "        self.name = name\n",
            "keyword-only parameters",
        ),
        (
            "class User(Base):\n"
            "    def __init__(self, *, name: str) -> None:\n"
            "        if not name:\n"
            "            raise ValueError(\"name\")\n"
            "        self.name = name\n",
            "without bases",
        ),
        (
            "class User:\n"
            "    def __init__(self, *, name: str) -> None:\n"
            "        if not name:\n"
            "            raise ValueError(\"name\")\n"
            "        self.name = name\n"
            "\n"
            "    @property\n"
            "    def display_name(self) -> str:\n"
            "        return self.name\n",
            "descriptors and class data are unsupported",
        ),
        (
            "class User:\n"
            "    def __init__(self, *, first: str, last: str) -> None:\n"
            "        if not first or not last:\n"
            "            raise ValueError(\"name\")\n"
            "        self.first = first\n"
            "        self.last = last\n",
            "exactly one field",
        ),
        (
            "class User:\n"
            "    def __init__(self, *, name: str) -> None:\n"
            "        if not name:\n"
            "            raise TypeError(\"name\")\n"
            "        self.name = name\n",
            "raise ValueError",
        ),
        (
            "class Sample:\n"
            "    def __init__(self, *, len: int) -> None:\n"
            "        if not len:\n"
            "            raise ValueError(\"len\")\n"
            "        self.len = len\n",
            "reserved validation name",
        ),
    ],
)
async def test_convert_to_pydantic_rejects_semantic_risk_without_writing(
    tmp_path: Path,
    source: str,
    error: str,
) -> None:
    target = tmp_path / "models.py"
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    with pytest.raises(BackendError, match=error):
        class_name = "Sample" if source.startswith("class Sample:") else "User"
        await refactoring.convert_to_pydantic(pyright, str(target), class_name)

    assert target.read_text(encoding="utf-8") == source
    pyright.notify_file_changed.assert_not_awaited()


# ── convert_to_typeddict (consistent dict-literal returns) ──


def _type_info(type_string: str) -> TypeInfo:
    return TypeInfo(expression="value", type_string=type_string, source="pyright")


@pytest.mark.asyncio
async def test_convert_to_typeddict_preview_preserves_source(tmp_path: Path) -> None:
    target = tmp_path / "payloads.py"
    source = (
        "def make_user(name: str, enabled: bool) -> dict[str, object]:\n"
        '    return {"name": name, "enabled": enabled}\n'
    )
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_hover.side_effect = [_type_info("str"), _type_info("bool")]

    result = await refactoring.convert_to_typeddict(
        pyright,
        str(target),
        "make_user",
        "UserPayload",
    )

    assert result.applied is False
    assert target.read_text(encoding="utf-8") == source
    assert len(result.edits) == 1
    converted = result.edits[0].new_text
    assert "from typing import TypedDict" in converted
    assert "class UserPayload(TypedDict):\n    name: str\n    enabled: bool\n" in converted
    assert "def make_user(name: str, enabled: bool) -> UserPayload:" in converted
    compile(converted, str(target), "exec")
    assert pyright.get_hover.await_count == 2
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_convert_to_typeddict_accepts_consistent_branch_types(tmp_path: Path) -> None:
    target = tmp_path / "payloads.py"
    target.write_text(
        "def make_user(enabled: bool):\n"
        "    if enabled:\n"
        '        return {"name": "ready", "enabled": enabled}\n'
        '    return {"name": "waiting", "enabled": enabled}\n',
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_hover.side_effect = [
        _type_info("Literal['ready']"),
        _type_info("bool"),
        _type_info("Literal['waiting']"),
        _type_info("bool"),
    ]

    result = await refactoring.convert_to_typeddict(
        pyright,
        str(target),
        "make_user",
        "UserPayload",
    )

    converted = result.edits[0].new_text
    assert "name: str" in converted
    assert "enabled: bool" in converted
    compile(converted, str(target), "exec")
    assert pyright.get_hover.await_count == 4


@pytest.mark.asyncio
async def test_convert_to_typeddict_apply_writes_and_refreshes(tmp_path: Path) -> None:
    target = tmp_path / "payloads.py"
    target.write_text(
        "import typing as t\n\n"
        "def make_user(name: str):\n"
        '    return {"name": name}\n',
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_hover.return_value = _type_info("(variable) name: builtins.str")
    pyright.get_diagnostics.return_value = []

    result = await refactoring.convert_to_typeddict(
        pyright,
        str(target),
        "make_user",
        "UserPayload",
        apply=True,
    )

    assert result.applied is True
    converted = target.read_text(encoding="utf-8")
    assert "class UserPayload(t.TypedDict):" in converted
    assert "from typing import TypedDict" not in converted
    pyright.notify_file_changed.assert_awaited_once_with(str(target))
    pyright.get_diagnostics.assert_awaited_once_with(str(target))


@pytest.mark.asyncio
async def test_convert_to_typeddict_does_not_reuse_late_import(tmp_path: Path) -> None:
    target = tmp_path / "payloads.py"
    target.write_text(
        "def payload(name: str):\n"
        '    return {"name": name}\n'
        "\n"
        "from typing import TypedDict as LateTypedDict\n",
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_hover.return_value = _type_info("str")

    result = await refactoring.convert_to_typeddict(
        pyright,
        str(target),
        "payload",
        "Payload",
    )

    converted = result.edits[0].new_text
    assert converted.startswith("from typing import TypedDict\n\nclass Payload(TypedDict):")
    assert "from typing import TypedDict as LateTypedDict" in converted
    compile(converted, str(target), "exec")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,error",
    [
        (
            "def payload(name: str):\n"
            '    return {"name": name}\n'
            "\n"
            "class Payload:\n"
            "    pass\n",
            "already exists",
        ),
        (
            "def payload(key: str, value: str):\n"
            "    return {key: value}\n",
            "valid identifiers",
        ),
        (
            "def payload(flag: bool):\n"
            "    if flag:\n"
            '        return {"name": "ready"}\n'
            '    return {"name": "waiting", "enabled": flag}\n',
            "same ordered keys",
        ),
        (
            "def payload(name: str) -> str:\n"
            '    return {"name": name}\n',
            "dict/mapping return annotations",
        ),
    ],
)
async def test_convert_to_typeddict_rejects_unsafe_shapes(
    tmp_path: Path,
    source: str,
    error: str,
) -> None:
    target = tmp_path / "payloads.py"
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    with pytest.raises(BackendError, match=error):
        await refactoring.convert_to_typeddict(
            pyright,
            str(target),
            "payload",
            "Payload",
        )

    assert target.read_text(encoding="utf-8") == source
    pyright.get_hover.assert_not_awaited()


@pytest.mark.asyncio
async def test_convert_to_typeddict_rejects_inconsistent_inferred_types(tmp_path: Path) -> None:
    target = tmp_path / "payloads.py"
    source = (
        "def payload(flag: bool):\n"
        "    if flag:\n"
        '        return {"value": 1}\n'
        '    return {"value": "one"}\n'
    )
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_hover.side_effect = [_type_info("int"), _type_info("str")]

    with pytest.raises(BackendError, match="inconsistent inferred types"):
        await refactoring.convert_to_typeddict(
            pyright,
            str(target),
            "payload",
            "Payload",
        )

    assert target.read_text(encoding="utf-8") == source


@pytest.mark.asyncio
async def test_convert_to_typeddict_rejects_unknown_inferred_type(tmp_path: Path) -> None:
    target = tmp_path / "payloads.py"
    source = "def payload(value):\n    return {\"value\": value}\n"
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_hover.return_value = _type_info("Unknown")

    with pytest.raises(BackendError, match="could not infer a concrete type"):
        await refactoring.convert_to_typeddict(
            pyright,
            str(target),
            "payload",
            "Payload",
        )

    assert target.read_text(encoding="utf-8") == source


@pytest.mark.parametrize("converter_name", ["dataclass", "pydantic", "typeddict"])
@pytest.mark.asyncio
async def test_semantic_converters_reject_drift_between_planning_and_transform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    converter_name: str,
) -> None:
    target = tmp_path / "models.py"
    pyright = AsyncMock()
    pyright.get_hover.return_value = _type_info("str")
    converter_module: ModuleType

    if converter_name == "dataclass":
        source = (
            "class User:\n"
            "    def __init__(self, name: str):\n"
            "        self.name = name\n"
        )
        converter_module = dataclass_conversion
    elif converter_name == "pydantic":
        source = (
            "class User:\n"
            "    def __init__(self, *, name: str) -> None:\n"
            "        if not name:\n"
            "            raise ValueError('name required')\n"
            "        self.name = name\n"
        )
        converter_module = pydantic_conversion
    else:
        source = "def payload(name: str):\n    return {'name': name}\n"
        converter_module = typed_dict_conversion

    target.write_text(source, encoding="utf-8")
    newer_source = "external = True\n"

    def inject_drift(
        file_path: str,
        transformer: cst.CSTTransformer,
        *,
        apply: bool = False,
        source_snapshot: CstSourceSnapshot | None = None,
    ) -> tuple[list[TextEdit], list[str]]:
        target.write_text(newer_source, encoding="utf-8")
        return apply_cst_transformer_direct(
            file_path,
            transformer,
            apply=apply,
            source_snapshot=source_snapshot,
        )

    monkeypatch.setattr(converter_module, "apply_cst_transformer", inject_drift)

    with pytest.raises(BackendError, match="Stale edit source changed during CST planning"):
        if converter_name == "dataclass":
            await refactoring.convert_to_dataclass(pyright, str(target), "User")
        elif converter_name == "pydantic":
            await refactoring.convert_to_pydantic(pyright, str(target), "User")
        else:
            await refactoring.convert_to_typeddict(
                pyright,
                str(target),
                "payload",
                "Payload",
            )

    assert target.read_text(encoding="utf-8") == newer_source


_SUPERCLASS_SOURCE = (
    "class Foo:\n"
    "    shared = 1\n\n"
    "    def bar(self):\n"
    "        return 1\n\n"
    "    def baz(self):\n"
    "        return 2\n"
)


@pytest.mark.asyncio
async def test_extract_superclass_preview_does_not_write(tmp_path: Path) -> None:
    """Preview mode emits a whole-file edit but leaves disk untouched."""
    target = tmp_path / "m.py"
    target.write_text(_SUPERCLASS_SOURCE, encoding="utf-8")
    pyright = AsyncMock()

    result = await refactoring.extract_superclass(
        pyright, str(target), "Foo", "Base", ["bar", "shared"], apply=False
    )

    assert result.applied is False
    assert len(result.edits) == 1
    new_text = result.edits[0].new_text
    assert "class Base:" in new_text
    assert "class Foo(Base):" in new_text
    assert target.read_text(encoding="utf-8") == _SUPERCLASS_SOURCE
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_superclass_apply_writes_and_refreshes(tmp_path: Path) -> None:
    """``apply=True`` rewrites the file and notifies Pyright."""
    target = tmp_path / "m.py"
    target.write_text(_SUPERCLASS_SOURCE, encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await refactoring.extract_superclass(
        pyright, str(target), "Foo", "Base", ["bar"], apply=True
    )

    assert result.applied is True
    written = target.read_text(encoding="utf-8")
    assert "class Base:" in written
    assert "class Foo(Base):" in written
    assert "def baz" in written  # baz stayed on Foo
    pyright.notify_file_changed.assert_awaited()


@pytest.mark.asyncio
async def test_extract_superclass_missing_member_raises(tmp_path: Path) -> None:
    """A requested member absent from the class body raises ``BackendError``."""
    from python_refactor_mcp.errors import BackendError

    target = tmp_path / "m.py"
    target.write_text(_SUPERCLASS_SOURCE, encoding="utf-8")
    pyright = AsyncMock()

    with pytest.raises(BackendError, match="not found"):
        await refactoring.extract_superclass(
            pyright, str(target), "Foo", "Base", ["nonexistent"], apply=False
        )


@pytest.mark.asyncio
async def test_extract_superclass_rejects_property_member(tmp_path: Path) -> None:
    """A ``@property`` member cannot be hoisted."""
    from python_refactor_mcp.errors import BackendError

    target = tmp_path / "m.py"
    target.write_text(
        "class Foo:\n    @property\n    def value(self):\n        return 1\n",
        encoding="utf-8",
    )
    pyright = AsyncMock()

    with pytest.raises(BackendError, match="property"):
        await refactoring.extract_superclass(
            pyright, str(target), "Foo", "Base", ["value"], apply=False
        )


@pytest.mark.asyncio
async def test_extract_superclass_missing_class_raises(tmp_path: Path) -> None:
    """A class name absent from the file raises ``BackendError``."""
    from python_refactor_mcp.errors import BackendError

    target = tmp_path / "m.py"
    target.write_text(_SUPERCLASS_SOURCE, encoding="utf-8")
    pyright = AsyncMock()

    with pytest.raises(BackendError, match="not found"):
        await refactoring.extract_superclass(
            pyright, str(target), "Missing", "Base", ["bar"], apply=False
        )


@pytest.mark.asyncio
async def test_extract_superclass_empty_members_raises(tmp_path: Path) -> None:
    """An empty members list raises ``BackendError``."""
    from python_refactor_mcp.errors import BackendError

    target = tmp_path / "m.py"
    target.write_text(_SUPERCLASS_SOURCE, encoding="utf-8")
    pyright = AsyncMock()

    with pytest.raises(BackendError, match="at least one member"):
        await refactoring.extract_superclass(
            pyright, str(target), "Foo", "Base", [], apply=False
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "base_name", "members", "error"),
    [
        (_SUPERCLASS_SOURCE, "Foo", ["bar"], "must differ"),
        ("Base = object\n\n" + _SUPERCLASS_SOURCE, "Base", ["bar"], "already bound"),
        (_SUPERCLASS_SOURCE, "Base", ["bar", "bar"], "duplicates"),
        ("class Foo: shared = 1\n", "Base", ["shared"], "one-line class"),
        ("class Foo:\n    shared = 1; other = 2\n", "Base", ["shared"], "not found"),
        (
            "class Foo:\n    def bar(self):\n        pass\n\n"
            "class Foo:\n    def bar(self):\n        pass\n",
            "Base",
            ["bar"],
            "Multiple top-level",
        ),
    ],
)
async def test_extract_superclass_preflight_rejects_ambiguous_requests_without_writing(
    tmp_path: Path,
    source: str,
    base_name: str,
    members: list[str],
    error: str,
) -> None:
    """Collision and ambiguity failures leave the preview target byte-identical."""
    target = tmp_path / "m.py"
    target.write_text(source, encoding="utf-8")

    with pytest.raises(BackendError, match=error):
        await refactoring.extract_superclass(
            AsyncMock(), str(target), "Foo", base_name, members, apply=False
        )

    assert target.read_text(encoding="utf-8") == source


@pytest.mark.asyncio
async def test_extract_superclass_ignores_nested_class_with_same_name(tmp_path: Path) -> None:
    """Only the unique top-level source class is transformed."""
    source = (
        "class Container:\n"
        "    class Foo:\n"
        "        def bar(self):\n"
        "            return 'nested'\n\n"
        "class Foo:\n"
        "    def bar(self):\n"
        "        return 'top-level'\n"
    )
    target = tmp_path / "m.py"
    target.write_text(source, encoding="utf-8")

    result = await refactoring.extract_superclass(
        AsyncMock(), str(target), "Foo", "Base", ["bar"], apply=False
    )

    new_text = result.edits[0].new_text
    assert "class Container:\n    class Foo:\n        def bar" in new_text
    assert "class Foo(Base):\n    pass" in new_text
    assert new_text.count("class Base:") == 1
    assert target.read_text(encoding="utf-8") == source


_EXTRACT_CLASS_SOURCE = (
    "class Order:\n"
    "    def __init__(self, subtotal: float, tax: float, label: str):\n"
    "        self.label = label\n"
    "        self.subtotal: float = subtotal\n"
    "        self.tax = tax\n\n"
    "    def total(self, discount: float = 0, *, floor: float = 0) -> float:\n"
    "        return max(self.subtotal + self.tax - discount, floor)\n\n"
    "    def summary(self) -> str:\n"
    '        return f"{self.label}: {self.total()}"\n'
)


@pytest.mark.asyncio
async def test_extract_class_preview_preserves_delegated_public_surface(tmp_path: Path) -> None:
    """Preview moves cohesive state/behavior while the source API remains usable."""
    target = tmp_path / "order.py"
    target.write_text(_EXTRACT_CLASS_SOURCE, encoding="utf-8")
    pyright = AsyncMock()

    result = await refactoring.extract_class(
        pyright,
        str(target),
        "Order",
        "Pricing",
        ["subtotal", "tax", "total"],
        "_pricing",
        apply=False,
    )

    assert result.applied is False
    assert len(result.edits) == 1
    transformed = result.edits[0].new_text
    assert "class Pricing:" in transformed
    assert "self._pricing = Pricing()" in transformed
    assert "self._pricing.subtotal: float = subtotal" in transformed
    assert "return self._pricing.total(discount, floor=floor)" in transformed
    assert "@subtotal.setter" in transformed
    assert target.read_text(encoding="utf-8") == _EXTRACT_CLASS_SOURCE

    namespace: dict[str, object] = {}
    exec(compile(transformed, str(target), "exec"), namespace)  # noqa: S102
    order_type = namespace["Order"]
    assert isinstance(order_type, type)
    order = order_type(10.0, 2.0, "invoice")
    assert order.total() == 12.0
    order.subtotal = 20.0
    assert order.summary() == "invoice: 22.0"
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_class_apply_writes_and_refreshes_diagnostics(tmp_path: Path) -> None:
    """Apply mode atomically writes the transform and refreshes diagnostics."""
    target = tmp_path / "order.py"
    target.write_text(_EXTRACT_CLASS_SOURCE, encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await refactoring.extract_class(
        pyright,
        str(target),
        "Order",
        "Pricing",
        ["subtotal", "tax", "total"],
        "_pricing",
        apply=True,
    )

    assert result.applied is True
    assert "class Pricing:" in target.read_text(encoding="utf-8")
    pyright.notify_file_changed.assert_awaited_once_with(str(target))
    pyright.get_diagnostics.assert_awaited_once_with(str(target))


@pytest.mark.asyncio
async def test_extract_class_rejects_method_dependency_left_on_source(tmp_path: Path) -> None:
    """A moved method cannot silently lose access to an unselected source member."""
    target = tmp_path / "order.py"
    target.write_text(_EXTRACT_CLASS_SOURCE, encoding="utf-8")
    pyright = AsyncMock()

    with pytest.raises(BackendError, match="unselected self member"):
        await refactoring.extract_class(
            pyright,
            str(target),
            "Order",
            "Presentation",
            ["summary"],
            "_presentation",
        )

    assert target.read_text(encoding="utf-8") == _EXTRACT_CLASS_SOURCE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("members", "new_class_name", "collaborator_attribute", "error"),
    [
        (["tax", "tax"], "Pricing", "_pricing", "unique"),
        (["tax"], "Order", "_pricing", "differ"),
        (["missing"], "Pricing", "_pricing", "not a direct"),
        (["tax"], "Pricing", "label", "already exists"),
    ],
)
async def test_extract_class_rejects_invalid_or_colliding_requests(
    tmp_path: Path,
    members: list[str],
    new_class_name: str,
    collaborator_attribute: str,
    error: str,
) -> None:
    """Invalid requests fail before writing the source file."""
    target = tmp_path / "order.py"
    target.write_text(_EXTRACT_CLASS_SOURCE, encoding="utf-8")

    with pytest.raises(BackendError, match=error):
        await refactoring.extract_class(
            AsyncMock(),
            str(target),
            "Order",
            new_class_name,
            members,
            collaborator_attribute,
        )

    assert target.read_text(encoding="utf-8") == _EXTRACT_CLASS_SOURCE
