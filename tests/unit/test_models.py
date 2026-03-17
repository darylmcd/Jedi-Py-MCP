"""Unit tests for shared Pydantic models."""

from __future__ import annotations

from python_refactor_mcp.models import (
    CallHierarchyItem,
    CallHierarchyResult,
    ConstructorSite,
    DeadCodeItem,
    Diagnostic,
    ImportSuggestion,
    Location,
    Position,
    Range,
    RefactorResult,
    ReferenceResult,
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
