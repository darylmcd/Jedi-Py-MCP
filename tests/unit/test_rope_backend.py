"""Unit tests for the rope backend implementation."""

from __future__ import annotations

from pathlib import Path

import pytest
from rope.base.fscommands import FileSystemCommands  # type: ignore[import-untyped]
from rope.contrib.autoimport.sqlite import AutoImport  # type: ignore[import-untyped]

from python_refactor_mcp.backends.rope_backend import RopeBackend
from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import RopeError, ToolInputError
from python_refactor_mcp.models import RefactorResult, SignatureOperation
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


@pytest.mark.asyncio
async def test_inline_default_removes_default_and_inlines_call_sites(tmp_path: Path) -> None:
    """Real rope inlines the default at call sites AND drops it from the definition."""
    module = tmp_path / "m.py"
    module.write_text(
        "def helper(a: int, b: int = 2) -> int:\n    return a + b\n\n\nhelper(1)\n",
        encoding="utf-8",
    )
    backend = RopeBackend(_config(tmp_path))
    backend.initialize()

    ops = [SignatureOperation(op="inline_default", index=1)]
    result = await backend.change_signature(str(module), 0, 4, ops, apply=False)
    edit = next(e for e in result.edits if Path(e.file_path).resolve() == module.resolve())

    assert "= 2" not in edit.new_text.splitlines()[0]
    assert "helper(1, 2)" in edit.new_text
    fixed = restore_signature_metadata(module.read_text(encoding="utf-8"), edit.new_text, 0, 4, ops)
    assert "def helper(a: int, b: int) -> int:" in fixed
    assert "helper(1, 2)" in fixed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "index", "reason"),
    [
        ("def f(a, b=2):\n    return b\n", 0, "has no default"),
        ("def f(a=1, b=2):\n    return b\n", 1, "earlier parameter(s) at index 0"),
        ("def f(a, b=2):\n    return b\n", 5, "out of range"),
    ],
)
async def test_inline_default_rejects_invalid_targets(
    tmp_path: Path, source: str, index: int, reason: str
) -> None:
    """inline_default targets rope would mishandle raise ToolInputError naming index."""
    module = tmp_path / "m.py"
    module.write_text(source, encoding="utf-8")
    backend = RopeBackend(_config(tmp_path))
    backend.initialize()

    with pytest.raises(ToolInputError) as exc_info:
        await backend.change_signature(
            str(module), 0, 4, [SignatureOperation(op="inline_default", index=index)], apply=False
        )

    assert reason in str(exc_info.value)
    assert "(parameter: index)" in str(exc_info.value)
    assert module.read_text(encoding="utf-8") == source


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
async def test_split_module_is_coherent_in_preview_and_apply(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    alpha = tmp_path / "alpha.py"
    beta = tmp_path / "beta.py"
    consumer = tmp_path / "consumer.py"
    originals = {
        source: (
            "class Beta:\n"
            "    pass\n"
            "\n"
            "class Alpha:\n"
            "    def make(self):\n"
            "        return Beta()\n"
        ),
        alpha: "",
        beta: "",
        consumer: "from source import Alpha, Beta\n\na = Alpha()\nb = Beta()\n",
    }
    for path, content in originals.items():
        path.write_text(content, encoding="utf-8")

    backend = RopeBackend(_config(tmp_path))
    backend.initialize()
    targets = {str(alpha): ["Alpha"], str(beta): ["Beta"]}

    preview = await backend.split_module(str(source), targets, apply=False)

    assert preview.applied is False
    edits = {Path(edit.file_path).resolve(): edit.new_text for edit in preview.edits}
    assert set(edits) == {source.resolve(), alpha.resolve(), beta.resolve(), consumer.resolve()}
    assert "import beta" in edits[alpha.resolve()]
    assert "return beta.Beta()" in edits[alpha.resolve()]
    assert "class Beta" in edits[beta.resolve()]
    assert "import alpha" in edits[consumer.resolve()]
    assert "a = alpha.Alpha()" in edits[consumer.resolve()]
    assert "b = beta.Beta()" in edits[consumer.resolve()]
    assert {path: path.read_text(encoding="utf-8") for path in originals} == originals

    applied = await backend.split_module(str(source), targets, apply=True)

    assert applied.applied is True
    assert source.read_text(encoding="utf-8").strip() == ""
    assert "return beta.Beta()" in alpha.read_text(encoding="utf-8")
    assert "class Beta" in beta.read_text(encoding="utf-8")
    assert "a = alpha.Alpha()" in consumer.read_text(encoding="utf-8")


def test_symbol_lookup_rejects_reference_without_definition(tmp_path: Path) -> None:
    module = tmp_path / "consumer.py"
    module.write_text("from provider import Missing\n\nprint(Missing)\n", encoding="utf-8")
    backend = RopeBackend(_config(tmp_path))
    backend.initialize()

    with pytest.raises(RopeError, match="one top-level definition"):
        backend._find_symbol_offset(  # pyright: ignore[reportPrivateUsage]
            str(module),
            "Missing",
        )


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


@pytest.mark.asyncio
async def test_autoimport_builds_lazily_without_process_pool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rope.contrib.autoimport.sqlite as rope_autoimport_sqlite  # type: ignore[import-untyped]

    def no_process_pool(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("AutoImport must not spawn a process pool")

    monkeypatch.setattr(rope_autoimport_sqlite, "ProcessPoolExecutor", no_process_pool)
    (tmp_path / "calc.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8"
    )
    backend = RopeBackend(_config(tmp_path))
    backend.initialize()
    try:
        assert backend._autoimport is None  # pyright: ignore[reportPrivateUsage]

        results = await backend.autoimport_search("add")

        assert ("from calc import add", "add") in results
        assert backend._autoimport is not None  # pyright: ignore[reportPrivateUsage]
    finally:
        backend.close()


def _generate_fixture(tmp_path: Path, source: str) -> tuple[RopeBackend, Path]:
    module = tmp_path / "usage.py"
    module.write_text(source, encoding="utf-8")
    backend = RopeBackend(_config(tmp_path))
    backend.initialize()
    return backend, module


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "source", "expected"),
    [
        ("function", "def main():\n    return compute(1, 2)\n", "    def compute(arg0, arg1):\n        pass\n"),
        ("class", "item = Widget()\n", "class Widget(object):\n    pass\n"),
        ("variable", "print(missing_value)\n", "missing_value = None"),
    ],
)
async def test_generate_code_preview_inserts_definition(
    tmp_path: Path, kind: str, source: str, expected: str,
) -> None:
    """Real rope: each in-file kind previews a stub definition without writing it."""
    backend, module = _generate_fixture(tmp_path, source)
    name_line, name_col = next(
        (index, line.find(token))
        for index, line in enumerate(source.splitlines())
        for token in ("compute", "Widget", "missing_value")
        if token in line
    )

    result = await backend.generate_code(str(module), name_line, name_col, kind, apply=False)

    assert result.applied is False
    assert [Path(edit.file_path).resolve() for edit in result.edits] == [module.resolve()]
    assert expected in result.edits[0].new_text
    assert module.read_text(encoding="utf-8") == source


@pytest.mark.asyncio
async def test_generate_code_apply_writes_function_stub(tmp_path: Path) -> None:
    """apply=True writes the generated function stub into the usage module."""
    source = "def main():\n    return compute(1, 2)\n"
    backend, module = _generate_fixture(tmp_path, source)

    result = await backend.generate_code(str(module), 1, 11, "Function", apply=True)

    assert result.applied is True
    assert "    def compute(arg0, arg1):\n        pass\n" in module.read_text(encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["module", "package"])
async def test_generate_code_module_and_package_preview_adds_import(tmp_path: Path, kind: str) -> None:
    """Real rope: module/package kinds build a change set whose text edit imports the new name."""
    source = "helpers.run()\n"
    backend, module = _generate_fixture(tmp_path, source)

    result = await backend.generate_code(str(module), 0, 0, kind, apply=False)

    assert result.applied is False
    assert [Path(edit.file_path).resolve() for edit in result.edits] == [module.resolve()]
    assert "import helpers" in result.edits[0].new_text
    assert not (tmp_path / "helpers.py").exists()
    assert not (tmp_path / "helpers").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "created"),
    [("module", "helpers.py"), ("package", "helpers/__init__.py")],
)
async def test_generate_code_module_and_package_apply_creates_resource(
    tmp_path: Path, kind: str, created: str,
) -> None:
    """Real rope: apply=True creates the new module/package as well as writing the import."""
    source = "helpers.run()\n"
    backend, module = _generate_fixture(tmp_path, source)

    result = await backend.generate_code(str(module), 0, 0, kind, apply=True)

    assert result.applied is True
    assert (tmp_path / created).is_file()
    assert "import helpers" in module.read_text(encoding="utf-8")
    assert str(module.resolve()) in {str(Path(path).resolve()) for path in result.files_affected}
    # Post-apply diagnostics read every listed path, so folders are never listed.
    assert all(Path(path).is_file() for path in result.files_affected)
    assert (tmp_path / created).resolve() in {Path(op.path).resolve() for op in result.file_operations}


@pytest.mark.asyncio
async def test_generate_code_module_apply_keeps_existing_resource(tmp_path: Path) -> None:
    """A module that already exists is refused without touching it or the usage file."""
    source = "helpers.run()\n"
    backend, module = _generate_fixture(tmp_path, source)
    existing = tmp_path / "helpers.py"
    existing.write_text("KEEP = 1\n", encoding="utf-8")

    with pytest.raises(RopeError):
        await backend.generate_code(str(module), 0, 0, "module", apply=True)

    assert existing.read_text(encoding="utf-8") == "KEEP = 1\n"
    assert module.read_text(encoding="utf-8") == source


@pytest.mark.asyncio
async def test_generate_code_rejects_unknown_kind(tmp_path: Path) -> None:
    backend, module = _generate_fixture(tmp_path, "value = thing\n")

    with pytest.raises(RopeError, match="Unsupported generation kind: method"):
        await backend.generate_code(str(module), 0, 8, "method", apply=False)


def _resolved(path: str | None) -> Path | None:
    return None if path is None else Path(path).resolve()


def _file_ops(result: RefactorResult) -> list[tuple[str, Path | None, Path | None]]:
    return [(op.kind, _resolved(op.path), _resolved(op.new_path)) for op in result.file_operations]


def _move_fixture(tmp_path: Path, *, importer: bool) -> tuple[RopeBackend, Path, Path]:
    module = tmp_path / "mod.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "__init__.py").write_text("", encoding="utf-8")
    if importer:
        (tmp_path / "user.py").write_text("import mod\n\nprint(mod.VALUE)\n", encoding="utf-8")
    backend = RopeBackend(_config(tmp_path))
    backend.initialize()
    return backend, module, dest


@pytest.mark.asyncio
async def test_module_to_package_preview_lists_folder_and_move(tmp_path: Path) -> None:
    """Real rope: the preview names the new package folder and the module move, not an identity edit."""
    module = tmp_path / "pkgmod.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    backend = RopeBackend(_config(tmp_path))
    backend.initialize()

    result = await backend.module_to_package(str(module), apply=False)

    root = tmp_path.resolve()
    assert result.applied is False
    assert result.edits == []
    assert _file_ops(result) == [
        ("create_folder", root / "pkgmod", None),
        ("move", root / "pkgmod.py", root / "pkgmod" / "__init__.py"),
    ]
    assert [Path(path).resolve() for path in result.files_affected] == [root / "pkgmod" / "__init__.py"]
    assert module.is_file()
    assert not (tmp_path / "pkgmod").exists()


@pytest.mark.asyncio
async def test_module_to_package_apply_creates_package(tmp_path: Path) -> None:
    module = tmp_path / "pkgmod.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    backend = RopeBackend(_config(tmp_path))
    backend.initialize()

    result = await backend.module_to_package(str(module), apply=True)

    assert result.applied is True
    assert not module.exists()
    assert (tmp_path / "pkgmod" / "__init__.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert [Path(path).resolve() for path in result.files_affected] == [
        (tmp_path / "pkgmod" / "__init__.py").resolve(),
    ]


@pytest.mark.asyncio
async def test_move_module_preview_lists_move_without_importers(tmp_path: Path) -> None:
    """Real rope: a module nobody imports still reports its move in preview."""
    backend, module, dest = _move_fixture(tmp_path, importer=False)

    result = await backend.move_module(str(module), str(dest), apply=False)

    assert result.applied is False
    assert result.edits == []
    assert _file_ops(result) == [("move", module.resolve(), (dest / "mod.py").resolve())]
    assert [Path(path).resolve() for path in result.files_affected] == [(dest / "mod.py").resolve()]
    assert module.is_file()
    assert not (dest / "mod.py").exists()


@pytest.mark.asyncio
async def test_move_module_apply_moves_file_and_rewrites_importers(tmp_path: Path) -> None:
    """apply=True performs rope's move instead of writing only the importer edits."""
    backend, module, dest = _move_fixture(tmp_path, importer=True)
    user = tmp_path / "user.py"

    result = await backend.move_module(str(module), str(dest), apply=True)

    assert result.applied is True
    assert not module.exists()
    assert (dest / "mod.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert "dest.mod" in user.read_text(encoding="utf-8")
    assert _file_ops(result) == [("move", module.resolve(), (dest / "mod.py").resolve())]
    assert sorted(Path(path).resolve() for path in result.files_affected) == sorted(
        [(dest / "mod.py").resolve(), user.resolve()]
    )


@pytest.mark.asyncio
async def test_commit_change_stack_reports_file_operations(tmp_path: Path) -> None:
    """A move made under a change stack is kept on commit and listed in the committed result."""
    backend, module, dest = _move_fixture(tmp_path, importer=False)

    await backend.begin_change_stack()
    staged = await backend.move_module(str(module), str(dest), apply=True)
    committed = await backend.commit_change_stack()

    expected = [("move", module.resolve(), (dest / "mod.py").resolve())]
    assert _file_ops(staged) == expected
    assert _file_ops(committed) == expected
    assert [Path(path).resolve() for path in committed.files_affected] == [(dest / "mod.py").resolve()]
    assert not module.exists()
    assert (dest / "mod.py").is_file()


_HISTORY_SOURCE = "value = 1\nprint(value)\n"


def _history_fixture(tmp_path: Path) -> tuple[RopeBackend, Path]:
    module = tmp_path / "sample.py"
    module.write_text(_HISTORY_SOURCE, encoding="utf-8")
    backend = RopeBackend(_config(tmp_path))
    backend.initialize()
    return backend, module


@pytest.mark.asyncio
async def test_undo_on_empty_history_is_invalid_input(tmp_path: Path) -> None:
    """Empty undo history is the caller's state error, not a redacted backend failure."""
    backend, module = _history_fixture(tmp_path)

    with pytest.raises(ToolInputError, match=r"nothing to undo for count=1; the undo history holds 0"):
        await backend.undo()

    assert module.read_text(encoding="utf-8") == _HISTORY_SOURCE


@pytest.mark.asyncio
async def test_redo_on_empty_history_is_invalid_input(tmp_path: Path) -> None:
    backend, module = _history_fixture(tmp_path)

    with pytest.raises(ToolInputError, match=r"nothing to redo for count=1; the redo history holds 0"):
        await backend.redo()

    assert module.read_text(encoding="utf-8") == _HISTORY_SOURCE


@pytest.mark.asyncio
async def test_undo_count_beyond_history_undoes_nothing(tmp_path: Path) -> None:
    """A count larger than the history is rejected before the loop: no partial undo."""
    backend, module = _history_fixture(tmp_path)
    # A committed change stack records exactly one rope history entry.
    await backend.begin_change_stack()
    await backend.rename(str(module), 0, 0, "count", apply=True)
    await backend.commit_change_stack()
    renamed = module.read_text(encoding="utf-8")
    assert renamed == "count = 1\nprint(count)\n"

    with pytest.raises(ToolInputError, match=r"count=2; the undo history holds 1"):
        await backend.undo(2)

    assert module.read_text(encoding="utf-8") == renamed
    await backend.undo(1)
    assert module.read_text(encoding="utf-8") == _HISTORY_SOURCE


@pytest.mark.asyncio
async def test_commit_change_stack_without_begin_is_invalid_input(tmp_path: Path) -> None:
    backend, module = _history_fixture(tmp_path)

    with pytest.raises(ToolInputError, match=r"commit_change_stack: no active change stack"):
        await backend.commit_change_stack()

    assert module.read_text(encoding="utf-8") == _HISTORY_SOURCE


@pytest.mark.asyncio
async def test_rollback_change_stack_without_begin_is_invalid_input(tmp_path: Path) -> None:
    backend, module = _history_fixture(tmp_path)

    with pytest.raises(ToolInputError, match=r"rollback_change_stack: no active change stack"):
        await backend.rollback_change_stack()

    assert module.read_text(encoding="utf-8") == _HISTORY_SOURCE


@pytest.mark.asyncio
async def test_begin_change_stack_twice_is_invalid_input(tmp_path: Path) -> None:
    backend, module = _history_fixture(tmp_path)
    await backend.begin_change_stack()

    with pytest.raises(ToolInputError, match=r"begin_change_stack: a change stack is already active"):
        await backend.begin_change_stack()

    # The first stack is still active and usable; the project is unchanged.
    await backend.rollback_change_stack()
    assert module.read_text(encoding="utf-8") == _HISTORY_SOURCE
