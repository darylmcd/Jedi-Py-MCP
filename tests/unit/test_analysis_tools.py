"""Unit tests for analysis tool orchestration and fallback behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    CompletionItem,
    Diagnostic,
    DocumentationResult,
    DocumentHighlight,
    InlayHint,
    ParameterInfo,
    Position,
    Range,
    SemanticToken,
    SignatureInfo,
    TypeInfo,
)
from python_refactor_mcp.tools import analysis
from tests.helpers import make_location as _location


@pytest.mark.asyncio
async def test_find_references_falls_back_to_jedi_when_pyright_is_empty() -> None:
    """Ensure Jedi fallback runs when Pyright returns no references."""
    pyright = AsyncMock()
    jedi = AsyncMock()
    pyright.get_references.return_value = []
    jedi.get_references.return_value = [_location("/repo/a.py", 2, 1)]

    result = await analysis.find_references(pyright, jedi, "/repo/a.py", 2, 1)

    assert result.source == "jedi"
    assert result.total_count == 1
    pyright.get_references.assert_awaited_once()
    jedi.get_references.assert_awaited_once()


@pytest.mark.asyncio
async def test_find_references_merges_and_deduplicates_results() -> None:
    """Ensure merged reference results are de-duplicated and sorted."""
    pyright = AsyncMock()
    jedi = AsyncMock()

    shared = _location("/repo/a.py", 1, 2)
    pyright.get_references.return_value = [shared]
    jedi.get_references.return_value = [shared, _location("/repo/b.py", 3, 4)]

    result = await analysis.find_references(pyright, jedi, "/repo/a.py", 1, 2)

    assert result.source == "combined"
    assert result.total_count == 2
    assert [item.file_path for item in result.references] == ["/repo/a.py", "/repo/b.py"]


@pytest.mark.asyncio
async def test_find_references_keeps_pyright_results_when_jedi_fails() -> None:
    """Ensure Jedi errors do not fail a successful Pyright reference lookup."""
    pyright = AsyncMock()
    jedi = AsyncMock()

    pyright.get_references.return_value = [_location("/repo/a.py", 1, 2)]
    jedi.get_references.side_effect = RuntimeError("jedi failed")

    result = await analysis.find_references(pyright, jedi, "/repo/a.py", 1, 2)

    assert result.source == "pyright"
    assert result.total_count == 1
    assert result.references[0].file_path == "/repo/a.py"


@pytest.mark.asyncio
async def test_get_type_info_keeps_pyright_result_when_jedi_fails() -> None:
    """Ensure Jedi infer errors do not hide usable Pyright hover info."""
    pyright = AsyncMock()
    jedi = AsyncMock()

    pyright.get_hover.return_value = TypeInfo(
        expression="/repo/a.py:0:0",
        type_string="builtins.int",
        documentation=None,
        source="pyright",
    )
    jedi.infer_type.side_effect = RuntimeError("jedi failed")

    result = await analysis.get_type_info(pyright, jedi, "/repo/a.py", 0, 0)

    assert result.type_string == "builtins.int"
    assert result.source == "pyright"


@pytest.mark.asyncio
async def test_get_type_info_uses_jedi_when_pyright_is_unknown() -> None:
    """Ensure unknown Pyright hover falls back to Jedi inference."""
    pyright = AsyncMock()
    jedi = AsyncMock()

    pyright.get_hover.return_value = TypeInfo(
        expression="/repo/a.py:0:0",
        type_string="Unknown",
        documentation=None,
        source="pyright",
    )
    inferred = TypeInfo(
        expression="/repo/a.py:0:0",
        type_string="module.symbol.Type",
        documentation="doc",
        source="jedi",
    )
    jedi.infer_type.return_value = inferred

    result = await analysis.get_type_info(pyright, jedi, "/repo/a.py", 0, 0)

    assert result is inferred
    jedi.infer_type.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_diagnostics_filters_and_sorts() -> None:
    """Ensure diagnostics filtering is case-insensitive and output is sorted."""
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = [
        Diagnostic(
            file_path="/repo/b.py",
            range=Range(start=Position(line=9, character=0), end=Position(line=9, character=1)),
            severity="warning",
            message="warn",
            code=None,
        ),
        Diagnostic(
            file_path="/repo/a.py",
            range=Range(start=Position(line=1, character=1), end=Position(line=1, character=3)),
            severity="warning",
            message="warn2",
            code=None,
        ),
        Diagnostic(
            file_path="/repo/a.py",
            range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
            severity="error",
            message="err",
            code=None,
        ),
    ]

    filtered = await analysis.get_diagnostics(pyright, severity_filter="WARNING")

    assert [(item.file_path, item.range.start.line) for item in filtered] == [
        ("/repo/a.py", 1),
        ("/repo/b.py", 9),
    ]


@pytest.mark.asyncio
async def test_get_diagnostics_rejects_invalid_severity() -> None:
    """Ensure invalid severity values fail fast with a clear error."""
    pyright = AsyncMock()

    with pytest.raises(ValueError, match="Invalid severity_filter"):
        await analysis.get_diagnostics(pyright, severity_filter="critical")


@pytest.mark.asyncio
async def test_get_completions_sorts_results() -> None:
    """Ensure completions are returned in stable sorted order."""
    pyright = AsyncMock()
    pyright.get_completions.return_value = [
        CompletionItem(label="zeta", kind="function", detail=None, insert_text="zeta", documentation=None),
        CompletionItem(label="alpha", kind="function", detail=None, insert_text="alpha", documentation=None),
    ]

    result = await analysis.get_completions(pyright, "/repo/a.py", 0, 0)

    assert [item.label for item in result] == ["alpha", "zeta"]


@pytest.mark.asyncio
async def test_get_signature_help_passthrough() -> None:
    """Ensure signature help is returned unchanged from the analysis backend."""
    pyright = AsyncMock()
    signature = SignatureInfo(
        label="f(a: int, b: str)",
        parameters=[ParameterInfo(label="a: int"), ParameterInfo(label="b: str")],
        active_parameter=1,
        active_signature=0,
        documentation="doc",
    )
    pyright.get_signature_help.return_value = signature

    result = await analysis.get_signature_help(pyright, "/repo/a.py", 1, 5)

    assert result is signature


@pytest.mark.asyncio
async def test_get_documentation_passthrough() -> None:
    """Ensure Jedi documentation lookup is passed through unchanged."""
    jedi = AsyncMock()
    docs = DocumentationResult(file_path="/repo/a.py", line=0, character=0, entries=[])
    jedi.get_help.return_value = docs

    result = await analysis.get_documentation(jedi, "/repo/a.py", 0, 0)

    assert result is docs


@pytest.mark.asyncio
async def test_get_document_highlights_sorted() -> None:
    """Ensure highlight output is sorted deterministically."""
    pyright = AsyncMock()
    pyright.get_document_highlights.return_value = [
        DocumentHighlight(
            range=Range(start=Position(line=2, character=1), end=Position(line=2, character=3)),
            kind="read",
        ),
        DocumentHighlight(
            range=Range(start=Position(line=1, character=1), end=Position(line=1, character=3)),
            kind="write",
        ),
    ]

    result = await analysis.get_document_highlights(pyright, "/repo/a.py", 0, 0)

    assert [item.range.start.line for item in result] == [1, 2]


@pytest.mark.asyncio
async def test_get_inlay_hints_sorted() -> None:
    """Ensure inlay hints are sorted by position and label."""
    pyright = AsyncMock()
    pyright.get_inlay_hints.return_value = [
        InlayHint(position=Position(line=2, character=1), label=": int"),
        InlayHint(position=Position(line=1, character=1), label=": str"),
    ]

    result = await analysis.get_inlay_hints(pyright, "/repo/a.py", 0, 0, 3, 0)

    assert [item.position.line for item in result] == [1, 2]


@pytest.mark.asyncio
async def test_get_semantic_tokens_sorted() -> None:
    """Ensure semantic tokens are sorted by source position."""
    pyright = AsyncMock()
    pyright.get_semantic_tokens.return_value = [
        SemanticToken(
            range=Range(start=Position(line=3, character=1), end=Position(line=3, character=2)),
            token_type="variable",
            modifiers=[],
        ),
        SemanticToken(
            range=Range(start=Position(line=1, character=1), end=Position(line=1, character=2)),
            token_type="function",
            modifiers=[],
        ),
    ]

    result = await analysis.get_semantic_tokens(pyright, "/repo/a.py")

    assert [item.range.start.line for item in result] == [1, 3]


@pytest.mark.asyncio
async def test_get_workspace_diagnostics_aggregates_by_file(tmp_path: Path) -> None:
    """Ensure workspace diagnostics are aggregated into per-file counts."""
    file_a = tmp_path / "a.py"
    file_b = tmp_path / "b.py"
    file_a.write_text("x = 1\n", encoding="utf-8")
    file_b.write_text("y = 2\n", encoding="utf-8")

    pyright = AsyncMock()

    async def _diagnostics_for(file_path: str | None) -> list[Diagnostic]:
        if file_path == str(file_a.resolve()):
            return [
                Diagnostic(
                    file_path=str(file_a.resolve()),
                    range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
                    severity="error",
                    message="err",
                    code=None,
                ),
                Diagnostic(
                    file_path=str(file_a.resolve()),
                    range=Range(start=Position(line=0, character=2), end=Position(line=0, character=3)),
                    severity="warning",
                    message="warn",
                    code=None,
                ),
            ]
        if file_path == str(file_b.resolve()):
            return [
                Diagnostic(
                    file_path=str(file_b.resolve()),
                    range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
                    severity="hint",
                    message="hint",
                    code=None,
                )
            ]
        return []

    pyright.get_diagnostics.side_effect = _diagnostics_for
    config = ServerConfig(
        workspace_root=tmp_path,
        python_executable=tmp_path / ".venv" / "Scripts" / "python.exe",
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )

    result = await analysis.get_workspace_diagnostics(pyright, config)

    assert [(item.file_path, item.total_count) for item in result.items] == [
        (str(file_a.resolve()), 2),
        (str(file_b.resolve()), 1),
    ]


# ── PR 3-B: Invalid-input / failure-path unit tests ──


@pytest.mark.asyncio
async def test_find_references_jedi_fallback_exception_returns_partial() -> None:
    """When Pyright finds nothing and Jedi raises, return empty result."""
    pyright = AsyncMock()
    jedi = AsyncMock()
    pyright.get_references.return_value = []
    jedi.get_references.side_effect = RuntimeError("Jedi crashed")

    result = await analysis.find_references(pyright, jedi, "/repo/a.py", 0, 0)

    assert result.references == []
    assert result.total_count == 0


@pytest.mark.asyncio
async def test_get_type_info_both_backends_fail_returns_unknown() -> None:
    """When Pyright returns Unknown and Jedi raises, return Unknown TypeInfo."""
    pyright = AsyncMock()
    jedi = AsyncMock()
    pyright.get_hover.return_value = TypeInfo(
        expression="/repo/a.py:0:0",
        type_string="Unknown",
        documentation=None,
        source="pyright",
    )
    jedi.infer_type.side_effect = RuntimeError("Jedi crashed")

    result = await analysis.get_type_info(pyright, jedi, "/repo/a.py", 0, 0)

    assert result.type_string == "Unknown"
