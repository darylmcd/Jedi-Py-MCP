"""Unit tests for search tool orchestration and fallbacks."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.models import Diagnostic, ImportSuggestion, Location, Position, Range, SymbolInfo
from python_refactor_mcp.tools import search
from python_refactor_mcp.tools.search import _helpers as search_helpers
from python_refactor_mcp.tools.search._helpers import NameOccurrenceIndex, build_name_occurrence_index
from tests.helpers import make_config as _config


def _location(path: Path, line: int, character: int) -> Location:
    return Location(
        file_path=str(path.resolve()),
        range=Range(
            start=Position(line=line, character=character),
            end=Position(line=line, character=character + 1),
        ),
    )


@pytest.mark.asyncio
async def test_find_constructors_filters_for_call_sites(tmp_path: Path) -> None:
    """Ensure constructor search returns only real call sites for class usage."""
    source = tmp_path / "sample.py"
    source.write_text(
        "class Widget:\n"
        "    pass\n\n"
        "x = Widget(1, size=2)\n"
        "class Sub(Widget):\n"
        "    pass\n",
        encoding="utf-8",
    )

    pyright = AsyncMock()
    pyright.get_references.return_value = [
        _location(source, 0, 6),
        _location(source, 3, 4),
    ]

    result = await search.find_constructors(pyright, _config(tmp_path), "Widget", str(source))

    assert len(result.items) == 1
    assert result.items[0].class_name == "Widget"
    assert result.items[0].arguments == ["1", "size=2"]
    assert result.scan_failures == []


@pytest.mark.asyncio
async def test_find_constructors_reports_unparseable_files(tmp_path: Path) -> None:
    """An invalid candidate is a visible partial scan, not an empty success."""
    invalid = tmp_path / "invalid.py"
    invalid.write_text("class Widget(:\n", encoding="utf-8")

    result = await search.find_constructors(AsyncMock(), _config(tmp_path), "Widget")

    assert result.items == []
    assert result.files_scanned == 0
    assert len(result.scan_failures) == 1
    assert result.scan_failures[0].file_path == str(invalid.resolve())
    assert result.scan_failures[0].error_type == "SyntaxError"


@pytest.mark.asyncio
async def test_structural_search_returns_matches(tmp_path: Path) -> None:
    """Ensure structural search returns matched snippets and ranges."""
    source = tmp_path / "sample.py"
    source.write_text(
        "def f():\n"
        "    print('a')\n"
        "    print('b')\n",
        encoding="utf-8",
    )

    results, files_scanned, scan_failures = await search.structural_search(
        _config(tmp_path),
        "m.Call(func=m.Name('print'))",
        str(source),
    )

    assert len(results) == 2
    assert all("print" in item.matched_text for item in results)
    assert files_scanned == 1
    assert scan_failures == []


@pytest.mark.asyncio
async def test_structural_search_reports_parse_failures(tmp_path: Path) -> None:
    """Invalid files are visible to callers instead of disappearing from results."""
    (tmp_path / "valid.py").write_text("print('ok')\n", encoding="utf-8")
    invalid = tmp_path / "invalid.py"
    invalid.write_text("def broken(:\n", encoding="utf-8")

    results, files_scanned, scan_failures = await search.structural_search(
        _config(tmp_path), "m.Call(func=m.Name('print'))"
    )

    assert len(results) == 1
    assert files_scanned == 1
    assert len(scan_failures) == 1
    assert scan_failures[0].file_path == str(invalid.resolve())
    assert scan_failures[0].phase == "read_or_parse"


@pytest.mark.asyncio
async def test_dead_code_detection_marks_unreferenced_symbols(tmp_path: Path) -> None:
    """Ensure dead code detection flags symbols with zero references."""
    source = tmp_path / "sample.py"
    source.write_text(
        "def dead_func():\n"
        "    return 1\n\n"
        "class DeadClass:\n"
        "    pass\n",
        encoding="utf-8",
    )

    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []
    pyright.get_references.return_value = []

    result = await search.dead_code_detection(pyright, _config(tmp_path), str(source))

    names = {item.name for item in result.items}
    assert "dead_func" in names
    assert "DeadClass" in names


@pytest.mark.asyncio
async def test_dead_code_detection_keeps_once_referenced_same_file_helper(tmp_path: Path) -> None:
    """A helper called once in its own file is live; an uncalled sibling is still dead.

    ``get_references`` is queried with ``include_declaration=False``, so a single
    same-file reference is a real call site (regression: bl-0001).
    """
    source = tmp_path / "sample.py"
    source.write_text(
        "def _used_once():\n"
        "    return 1\n\n"
        "def _never_called():\n"
        "    return 2\n\n"
        "VALUE = _used_once()\n",
        encoding="utf-8",
    )

    async def _references(path: str, line: int, character: int, include_declaration: bool) -> list[Location]:
        assert include_declaration is False
        if line == 0:
            return [_location(source, 6, 8)]
        return []

    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []
    pyright.get_references.side_effect = _references

    result = await search.dead_code_detection(pyright, _config(tmp_path), str(source))

    names = {item.name for item in result.items}
    assert "_used_once" not in names
    assert "_never_called" in names


@pytest.mark.asyncio
async def test_dead_code_detection_ignores_declaration_self_reference(tmp_path: Path) -> None:
    """A reference located at the declaration itself is not a use of the symbol."""
    source = tmp_path / "sample.py"
    source.write_text("def dead_func():\n    return 1\n", encoding="utf-8")

    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []
    pyright.get_references.return_value = [_location(source, 0, 4)]

    result = await search.dead_code_detection(pyright, _config(tmp_path), str(source))

    assert {item.name for item in result.items} == {"dead_func"}


@pytest.mark.asyncio
async def test_dead_code_detection_reports_diagnostic_failures(tmp_path: Path) -> None:
    source = tmp_path / "sample.py"
    source.write_text("# no symbols\n", encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_diagnostics.side_effect = RuntimeError("backend unavailable")

    result = await search.dead_code_detection(pyright, _config(tmp_path), str(source))

    assert len(result.scan_failures) == 1
    assert result.scan_failures[0].file_path == str(source.resolve())
    assert result.scan_failures[0].error_type == "RuntimeError"


@pytest.mark.asyncio
async def test_suggest_imports_uses_jedi_fallback(tmp_path: Path) -> None:
    """Ensure suggest_imports falls back to Jedi when Pyright code actions are empty."""
    source = tmp_path / "sample.py"
    source.write_text("value = OrderedDict()\n", encoding="utf-8")

    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = [
        Diagnostic(
            file_path=str(source.resolve()),
            range=Range(
                start=Position(line=0, character=8),
                end=Position(line=0, character=19),
            ),
            severity="error",
            message="\"OrderedDict\" is not defined",
            code="reportUndefinedVariable",
        )
    ]
    pyright.get_code_actions.return_value = []

    jedi = AsyncMock()
    jedi.search_names.return_value = [
        ImportSuggestion(
            symbol="OrderedDict",
            module="collections",
            import_statement="from collections import OrderedDict",
        )
    ]

    suggestions = await search.suggest_imports(pyright, jedi, "OrderedDict", str(source))

    assert len(suggestions) == 1
    assert suggestions[0].module == "collections"


@pytest.mark.asyncio
async def test_search_symbols_merges_pyright_and_jedi_results() -> None:
    """Ensure symbol search merges and de-duplicates results across backends."""
    pyright = AsyncMock()
    jedi = AsyncMock()
    shared = SymbolInfo(
        name="Widget",
        kind="class",
        file_path="/repo/a.py",
        range=Range(start=Position(line=0, character=0), end=Position(line=0, character=6)),
        container=None,
    )
    pyright.workspace_symbol.return_value = [shared]
    jedi.search_symbols.return_value = [shared, SymbolInfo(
        name="WidgetFactory",
        kind="function",
        file_path="/repo/b.py",
        range=Range(start=Position(line=3, character=0), end=Position(line=3, character=13)),
        container=None,
    )]

    result = await search.search_symbols(pyright, jedi, "Widget")

    assert [item.name for item in result.items] == ["Widget", "WidgetFactory"]
    assert result.total_count == 2
    assert result.backend_failures == []

    limited = await search.search_symbols(pyright, jedi, "Widget", limit=1)
    assert [item.name for item in limited.items] == ["Widget"]
    assert limited.total_count == 2
    assert limited.truncated is True


# ── PR 3-B: Invalid-input / failure-path unit tests ──


@pytest.mark.asyncio
async def test_search_symbols_both_fail_reports_backend_failures() -> None:
    """When both backends raise, preserve stable failure provenance."""
    pyright = AsyncMock()
    jedi = AsyncMock()
    pyright.workspace_symbol.side_effect = RuntimeError("pyright crashed")
    jedi.search_symbols.side_effect = RuntimeError("jedi crashed")

    result = await search.search_symbols(pyright, jedi, "Widget")

    assert result.items == []
    assert [(failure.backend, failure.operation, failure.error_type) for failure in result.backend_failures] == [
        ("pyright", "workspace_symbol", "RuntimeError"),
        ("jedi", "search_symbols", "RuntimeError"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["dead_code_detection", "unused_symbol_sweep"])
async def test_symbol_scans_report_parse_failures(tool_name: str, tmp_path: Path) -> None:
    """A malformed file is a visible partial scan, not an empty success."""
    invalid = tmp_path / "invalid.py"
    invalid.write_text("def broken(:\n", encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await getattr(search, tool_name)(pyright, _config(tmp_path), str(invalid))

    assert result.items == []
    assert len(result.scan_failures) == 1
    assert result.scan_failures[0].file_path == str(invalid.resolve())
    assert result.scan_failures[0].phase == "symbol_scan"
    assert result.scan_failures[0].error_type == "SyntaxError"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["dead_code_detection", "unused_symbol_sweep"])
async def test_symbol_scans_report_missing_files(tool_name: str, tmp_path: Path) -> None:
    """An explicitly requested missing file remains visible in scan metadata."""
    missing = tmp_path / "missing.py"
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await getattr(search, tool_name)(pyright, _config(tmp_path), str(missing))

    assert result.items == []
    assert len(result.scan_failures) == 1
    assert result.scan_failures[0].file_path == str(missing.resolve())
    assert result.scan_failures[0].phase == "resolve"
    assert result.scan_failures[0].error_type == "FileNotFoundError"
    pyright.get_diagnostics.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["dead_code_detection", "unused_symbol_sweep"])
async def test_symbol_scans_report_missing_root_path(tool_name: str, tmp_path: Path) -> None:
    """A nonexistent root_path is a scan failure, never a clean empty result."""
    missing_root = tmp_path / "no-such-dir"
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await getattr(search, tool_name)(pyright, _config(tmp_path), root_path=str(missing_root))

    assert result.items == []
    assert [(f.file_path, f.phase, f.error_type) for f in result.scan_failures] == [
        (str(missing_root.resolve()), "resolve", "FileNotFoundError")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["dead_code_detection", "unused_symbol_sweep"])
async def test_symbol_scans_report_missing_file_paths_member(tool_name: str, tmp_path: Path) -> None:
    """A missing file_paths member is reported while the present members are still scanned."""
    present = tmp_path / "present.py"
    present.write_text("VALUE = 1\n", encoding="utf-8")
    missing = tmp_path / "missing.py"
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []
    pyright.get_references.return_value = [_location(tmp_path / "other.py", 0, 0)]

    result = await getattr(search, tool_name)(
        pyright, _config(tmp_path), file_paths=[str(present), str(missing)]
    )

    assert [(f.file_path, f.phase) for f in result.scan_failures] == [(str(missing.resolve()), "resolve")]
    pyright.get_references.assert_awaited()


@pytest.mark.asyncio
async def test_unused_symbol_sweep_flags_unreferenced_exports(tmp_path: Path) -> None:
    """Public exports with no cross-file references are flagged."""
    source = tmp_path / "api.py"
    source.write_text(
        "def public_unused():\n    return 1\n\nclass PublicWidget:\n    pass\n",
        encoding="utf-8",
    )

    pyright = AsyncMock()
    pyright.get_references.return_value = []

    result = await search.unused_symbol_sweep(pyright, _config(tmp_path), str(source))

    names = {item.name for item in result.items}
    assert "public_unused" in names
    assert "PublicWidget" in names


@pytest.mark.asyncio
async def test_unused_symbol_sweep_reports_reference_failures(tmp_path: Path) -> None:
    source = tmp_path / "api.py"
    source.write_text("def public_name():\n    return 1\n", encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_references.side_effect = RuntimeError("backend unavailable")

    result = await search.unused_symbol_sweep(pyright, _config(tmp_path), str(source))

    assert len(result.scan_failures) == 1
    assert result.scan_failures[0].subject == "public_name"


@pytest.mark.asyncio
async def test_unused_symbol_sweep_ignores_cross_file_referenced_exports(tmp_path: Path) -> None:
    """A symbol referenced from another file is not flagged."""
    source = tmp_path / "api.py"
    source.write_text("def used():\n    return 1\n", encoding="utf-8")
    other = tmp_path / "caller.py"

    pyright = AsyncMock()
    pyright.get_references.return_value = [_location(other, 0, 0)]

    result = await search.unused_symbol_sweep(pyright, _config(tmp_path), str(source))

    assert result.items == []


@pytest.mark.asyncio
async def test_unused_symbol_sweep_skips_externally_registered_symbols(tmp_path: Path) -> None:
    """Symbols decorated by an external registrar (mcp/tool) are skipped."""
    source = tmp_path / "api.py"
    source.write_text(
        "import mcp\n\n@mcp.tool\ndef registered():\n    return 1\n\ndef plain_unused():\n    return 2\n",
        encoding="utf-8",
    )

    pyright = AsyncMock()
    pyright.get_references.return_value = []

    result = await search.unused_symbol_sweep(pyright, _config(tmp_path), str(source))

    names = {item.name for item in result.items}
    assert "registered" not in names
    assert "plain_unused" in names


@pytest.mark.asyncio
async def test_unused_symbol_sweep_respects_dunder_all(tmp_path: Path) -> None:
    """Only __all__-listed names are in scope when the module defines __all__."""
    source = tmp_path / "api.py"
    source.write_text(
        '__all__ = ["exported"]\n\ndef exported():\n    return 1\n\ndef not_exported():\n    return 2\n',
        encoding="utf-8",
    )

    pyright = AsyncMock()
    pyright.get_references.return_value = []

    result = await search.unused_symbol_sweep(pyright, _config(tmp_path), str(source))

    names = {item.name for item in result.items}
    assert names == {"exported"}


# ── bl-0009: name-occurrence pre-filter for directory-wide sweeps ──


def _disable_occurrence_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force every candidate through the reference query (the pre-bl-0009 path)."""

    def _incomplete(*_args: object) -> NameOccurrenceIndex:
        return NameOccurrenceIndex(occurrences={}, complete=False)

    monkeypatch.setattr(search_helpers, "build_name_occurrence_index", _incomplete)


class _TextScanPyright:
    """Fake Pyright whose references are every whole-word occurrence of the queried name.

    Reads the same ``*.py``/``*.pyi`` files the occurrence index covers, so the
    pre-filter must agree with it exactly.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self.queried: list[str] = []

    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]:
        return []

    async def get_code_actions(
        self, file_path: str, range_value: Range, diagnostics: list[Diagnostic]
    ) -> list[dict[str, object]]:
        return []

    async def workspace_symbol(self, query: str) -> list[SymbolInfo]:
        return []

    async def get_references(
        self, file_path: str, line: int, char: int, include_declaration: bool
    ) -> list[Location]:
        source_line = Path(file_path).read_text(encoding="utf-8").splitlines()[line]
        name_match = re.match(r"\w+", source_line[char:])
        assert name_match is not None
        name = name_match.group(0)
        self.queried.append(name)
        pattern = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")
        locations: list[Location] = []
        for path in sorted([*self._root.rglob("*.py"), *self._root.rglob("*.pyi")]):
            for index, text in enumerate(path.read_text(encoding="utf-8").splitlines()):
                for match in pattern.finditer(text):
                    is_declaration = path.resolve() == Path(file_path).resolve() and (index, match.start()) == (
                        line,
                        char,
                    )
                    if include_declaration or not is_declaration:
                        locations.append(_location(path, index, match.start()))
        return locations


def _write_equivalence_workspace(root: Path) -> None:
    (root / "pkg").mkdir()
    (root / "pkg" / "core.py").write_text(
        '__all__ = ["exported_only", "listed_elsewhere", "helper_used_here", "stub_declared"]\n\n'
        "def exported_only():\n    return 1\n\n"
        "def listed_elsewhere():\n    return 2\n\n"
        "def helper_used_here():\n    return 3\n\n"
        "RESULT = helper_used_here()\n"
        "# mentions commented_twin — only in a comment\n"
        "def commented_twin():\n    return 4\n\n"
        "def stub_declared():\n    return 5\n",
        encoding="utf-8",
    )
    (root / "pkg" / "core.pyi").write_text("def stub_declared() -> int: ...\n", encoding="utf-8")
    (root / "pkg" / "consumer.py").write_text(
        "from pkg.core import listed_elsewhere\n\n"
        "def consumer_entry():\n    return listed_elsewhere()\n\n"
        "ORPHAN_CONSTANT = 7\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["dead_code_detection", "unused_symbol_sweep"])
async def test_symbol_scans_match_always_query_results(
    tool_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-filter returns exactly the results of querying every candidate."""
    _write_equivalence_workspace(tmp_path)
    tool = getattr(search, tool_name)

    filtered_backend = _TextScanPyright(tmp_path)
    filtered = await tool(filtered_backend, _config(tmp_path), root_path=str(tmp_path))
    _disable_occurrence_index(monkeypatch)
    baseline_backend = _TextScanPyright(tmp_path)
    baseline = await tool(baseline_backend, _config(tmp_path), root_path=str(tmp_path))

    assert filtered.model_dump() == baseline.model_dump()
    assert filtered.items, "fixture must produce dead candidates"
    assert len(filtered_backend.queried) < len(baseline_backend.queried)


@pytest.mark.asyncio
async def test_dead_code_detection_skips_lookup_for_sole_declaration(tmp_path: Path) -> None:
    """A name spelled only at its declaration is dead without a reference query."""
    _write_equivalence_workspace(tmp_path)
    backend = _TextScanPyright(tmp_path)

    result = await search.dead_code_detection(backend, _config(tmp_path), root_path=str(tmp_path))

    dead = {item.name for item in result.items}
    assert {"consumer_entry", "ORPHAN_CONSTANT"} <= dead
    assert "consumer_entry" not in backend.queried
    assert "ORPHAN_CONSTANT" not in backend.queried
    # Mentioned elsewhere (call site, __all__ string, comment, .pyi stub): always queried.
    assert {"helper_used_here", "exported_only", "commented_twin", "stub_declared"} <= set(backend.queried)


@pytest.mark.asyncio
async def test_unused_symbol_sweep_skips_lookup_for_names_absent_elsewhere(tmp_path: Path) -> None:
    """An export no other file spells is unused without a reference query."""
    _write_equivalence_workspace(tmp_path)
    backend = _TextScanPyright(tmp_path)

    result = await search.unused_symbol_sweep(backend, _config(tmp_path), root_path=str(tmp_path))

    assert "exported_only" in {item.name for item in result.items}
    assert "exported_only" not in backend.queried
    assert "helper_used_here" not in backend.queried
    # Spelled in consumer.py / core.pyi: queried, and the fake finds the cross-file uses.
    assert {"listed_elsewhere", "stub_declared"} <= set(backend.queried)
    assert "listed_elsewhere" not in {item.name for item in result.items}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["dead_code_detection", "unused_symbol_sweep"])
async def test_symbol_scans_of_explicit_files_query_every_candidate(tool_name: str, tmp_path: Path) -> None:
    """Explicit file targets skip the workspace-wide index and query every candidate."""
    _write_equivalence_workspace(tmp_path)
    backend = _TextScanPyright(tmp_path)

    await getattr(search, tool_name)(backend, _config(tmp_path), str(tmp_path / "pkg" / "consumer.py"))

    assert "consumer_entry" in backend.queried


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["dead_code_detection", "unused_symbol_sweep"])
async def test_symbol_scans_query_every_candidate_when_a_file_is_unreadable(
    tool_name: str, tmp_path: Path
) -> None:
    """A workspace file the index cannot decode disables every shortcut."""
    _write_equivalence_workspace(tmp_path)
    (tmp_path / "legacy.py").write_bytes(b"# \xff not utf-8\n")
    backend = _TextScanPyright(tmp_path)

    await getattr(search, tool_name)(backend, _config(tmp_path), root_path=str(tmp_path / "pkg"))

    assert "consumer_entry" in backend.queried


def test_name_occurrence_index_counts_non_ascii_and_nfkc_spellings(tmp_path: Path) -> None:
    """Tokens glued to non-ASCII text and NFKC-equivalent spellings are still counted."""
    declared = tmp_path / "declared.py"
    declared.write_text("value = 1\nother = 2\n", encoding="utf-8")
    (tmp_path / "user.py").write_text("x = ﬁle\n# value—\n", encoding="utf-8")

    index = build_name_occurrence_index(tmp_path, [declared], {"value", "file", "other"})

    assert index.complete is True
    resolved = str(declared.resolve())
    assert not index.mentioned_only_in("value", resolved)
    assert set(index.occurrences["file"]) == {str((tmp_path / "user.py").resolve())}
    assert index.mentioned_only_at_declaration("other", resolved)
