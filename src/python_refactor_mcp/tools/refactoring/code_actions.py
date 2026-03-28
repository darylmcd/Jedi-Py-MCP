"""Code action and import organization tools."""

from __future__ import annotations

from python_refactor_mcp.models import Position, Range, RefactorResult

from .helpers import (
    _attach_post_apply_diagnostics,
    _full_file_range,
    _PyrightRefactoringBackend,
    _range_contains_position,
    _result_from_text_edits,
    _workspace_edit_to_text_edits,
)


def _pick_code_action(actions: list[dict[str, object]], action_title: str | None = None) -> dict[str, object]:
    """Select a code action by title or fall back to the first available action."""
    if not actions:
        raise ValueError("No code actions were available for the requested location.")
    if action_title is None:
        return actions[0]

    lowered_title = action_title.strip().lower()
    for action in actions:
        title = action.get("title")
        if isinstance(title, str) and title.strip().lower() == lowered_title:
            return action
    for action in actions:
        title = action.get("title")
        if isinstance(title, str) and lowered_title in title.strip().lower():
            return action
    raise ValueError(f"Unable to find code action matching '{action_title}'.")


async def apply_code_action(
    pyright: _PyrightRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    action_title: str | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Apply or preview a Pyright code action at a source position."""
    diagnostics = await pyright.get_diagnostics(file_path)
    selected_diagnostics = [
        diagnostic
        for diagnostic in diagnostics
        if _range_contains_position(diagnostic.range, line, character)
    ]
    request_range = Range(
        start=Position(line=line, character=character),
        end=Position(line=line, character=character),
    )
    actions = await pyright.get_code_actions(file_path, request_range, selected_diagnostics)
    selected = _pick_code_action(actions, action_title)
    title = selected.get("title")
    description = title if isinstance(title, str) and title else "Applied code action"
    edits = _workspace_edit_to_text_edits(selected.get("edit"))
    if not edits:
        raise ValueError("Selected code action does not provide editable workspace changes.")
    result = _result_from_text_edits(edits, description, apply)
    return await _attach_post_apply_diagnostics(pyright, result)


async def organize_imports(
    pyright: _PyrightRefactoringBackend,
    file_path: str,
    apply: bool = False,
) -> RefactorResult:
    """Run organize imports for a file using available Pyright code actions."""
    actions = await pyright.get_code_actions(file_path, _full_file_range(file_path), [])
    organize_actions = [
        action
        for action in actions
        if (
            isinstance(action.get("kind"), str)
            and action.get("kind") == "source.organizeImports"
        )
        or (
            isinstance(action.get("title"), str)
            and "organize imports" in str(action.get("title")).strip().lower()
        )
    ]
    if not organize_actions:
        return RefactorResult(
            edits=[], files_affected=[], description="Imports already organized", applied=False,
        )
    selected = _pick_code_action(organize_actions, "organize imports")
    edits = _workspace_edit_to_text_edits(selected.get("edit"))
    if not edits:
        return RefactorResult(
            edits=[], files_affected=[], description="Imports already organized", applied=False,
        )
    result = _result_from_text_edits(edits, "Organized imports", apply)
    return await _attach_post_apply_diagnostics(pyright, result)
