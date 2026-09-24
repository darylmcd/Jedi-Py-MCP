"""Unit tests for shared Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from python_refactor_mcp.models import (
    CallHierarchyItem,
    CallHierarchyResult,
    ConstructorSite,
    DeadCodeItem,
    Diagnostic,
    FileOperation,
    ImportSuggestion,
    Location,
    Position,
    Range,
    RefactorResult,
    ReferenceResult,
    SignatureOperation,
    StructuralMatch,
    SymbolInfo,
    TextEdit,
    TypeInfo,
)


def _sample_range() -> Range:
    """Build a reusable sample range for model construction."""
    return Range(start=Position(line=1, character=2), end=Position(line=1, character=5))


def test_all_models_construct_and_round_trip() -> None:
    """Construct all Stage 1 models and verify basic serialization round-trip."""
    range_value = _sample_range()
    location = Location(file_path="C:/repo/sample.py", range=range_value)
    text_edit = TextEdit(file_path="C:/repo/sample.py", range=range_value, new_text="x")

    symbol = SymbolInfo(
        name="my_symbol",
        kind="function",
        file_path="C:/repo/sample.py",
        range=range_value,
        container="MyClass",
    )
    diagnostic = Diagnostic(
        file_path="C:/repo/sample.py",
        range=range_value,
        severity="warning",
        message="example",
        code="W001",
    )
    references = ReferenceResult(
        symbol="my_symbol",
        definition=location,
        references=[location],
        total_count=1,
        source="pyright",
    )
    type_info = TypeInfo(expression="x", type_string="int", documentation="number", source="pyright")

    call_item = CallHierarchyItem(
        name="my_func",
        kind="function",
        file_path="C:/repo/sample.py",
        range=range_value,
        detail="detail",
    )
    call_result = CallHierarchyResult(item=call_item, callers=[call_item], callees=[call_item])

    refactor = RefactorResult(
        edits=[text_edit],
        files_affected=["C:/repo/sample.py"],
        description="rename",
        applied=False,
        diagnostics_after=[diagnostic],
    )
    constructor = ConstructorSite(
        class_name="MyClass",
        file_path="C:/repo/sample.py",
        range=range_value,
        arguments=["a", "b"],
    )
    structural = StructuralMatch(file_path="C:/repo/sample.py", range=range_value, matched_text="MyClass()")
    dead_code = DeadCodeItem(
        name="unused",
        kind="function",
        file_path="C:/repo/sample.py",
        range=range_value,
        reason="no references",
    )
    import_suggestion = ImportSuggestion(
        symbol="Path",
        module="pathlib",
        import_statement="from pathlib import Path",
    )

    for model in (
        range_value,
        location,
        text_edit,
        symbol,
        diagnostic,
        references,
        type_info,
        call_item,
        call_result,
        refactor,
        constructor,
        structural,
        dead_code,
        import_suggestion,
    ):
        round_trip = model.__class__.model_validate(model.model_dump())
        assert round_trip == model


def test_refactor_result_default_applied_flag() -> None:
    """Verify refactor result defaults applied to False."""
    result = RefactorResult(edits=[], files_affected=[], description="placeholder")
    assert result.applied is False
    assert result.file_operations == []


def test_refactor_result_file_operations_round_trip() -> None:
    """File operations survive serialization beside the text edits."""
    result = RefactorResult(
        edits=[],
        files_affected=["C:/repo/pkg/__init__.py"],
        description="module to package",
        file_operations=[
            FileOperation(kind="create_folder", path="C:/repo/pkg"),
            FileOperation(kind="move", path="C:/repo/pkg.py", new_path="C:/repo/pkg/__init__.py"),
        ],
    )

    assert RefactorResult.model_validate(result.model_dump()) == result
    assert result.file_operations[0].new_path is None


def test_file_operation_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        FileOperation.model_validate({"kind": "copy", "path": "C:/repo/a.py"})


def test_signature_operation_rejects_negative_index() -> None:
    """A negative index is rejected instead of being Python-indexed by rope."""
    with pytest.raises(ValidationError) as exc_info:
        SignatureOperation(op="inline_default", index=-1)
    assert "index" in str(exc_info.value)
    assert SignatureOperation(op="inline_default", index=0).index == 0
    assert SignatureOperation(op="normalize").index is None


def test_signature_operation_rejects_negative_new_order_entry() -> None:
    """A negative reorder index fails validation instead of being silently dropped."""
    with pytest.raises(ValidationError) as exc_info:
        SignatureOperation(op="reorder", new_order=[1, -1, 0])
    errors = exc_info.value.errors()
    assert [error["loc"] for error in errors] == [("new_order", 1)]
    assert "new_order" in str(exc_info.value)
    assert SignatureOperation(op="reorder", new_order=[1, 0]).new_order == [1, 0]
    assert SignatureOperation(op="normalize").new_order is None
