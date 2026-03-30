"""Code action and import organization tools."""

from __future__ import annotations

from python_refactor_mcp.models import Position, Range, RefactorResult

from .helpers import (
    PyrightRefactoringBackend,
    full_file_range,
    post_apply_diagnostics,
    range_contains_position,
    result_from_text_edits,
    workspace_edit_to_text_edits,
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
    pyright: PyrightRefactoringBackend,
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
        if range_contains_position(diagnostic.range, line, character)
    ]
    request_range = Range(
        start=Position(line=line, character=character),
        end=Position(line=line, character=character),
    )
    actions = await pyright.get_code_actions(file_path, request_range, selected_diagnostics)
    selected = _pick_code_action(actions, action_title)
    title = selected.get("title")
    description = title if isinstance(title, str) and title else "Applied code action"
    edits = workspace_edit_to_text_edits(selected.get("edit"))
    if not edits:
        raise ValueError("Selected code action does not provide editable workspace changes.")
    result = result_from_text_edits(edits, description, apply)
    return await post_apply_diagnostics(pyright, result)


async def organize_imports(
    pyright: PyrightRefactoringBackend,
    file_path: str,
    apply: bool = False,
    file_paths: list[str] | None = None,
) -> RefactorResult:
    """Run organize imports for one or multiple files using Pyright code actions."""
    targets = file_paths if file_paths is not None else [file_path]
    all_edits: list[object] = []
    all_files: list[str] = []
    for fp in targets:
        actions = await pyright.get_code_actions(fp, full_file_range(fp), [])
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
            continue
        selected = _pick_code_action(organize_actions, "organize imports")
        edits = workspace_edit_to_text_edits(selected.get("edit"))
        all_edits.extend(edits)
        all_files.append(fp)

    if not all_edits:
        return RefactorResult(
            edits=[], files_affected=[], description="Imports already organized", applied=False,
        )
    result = result_from_text_edits(all_edits, f"Organized imports in {len(all_files)} file(s)", apply)
    return await post_apply_diagnostics(pyright, result)
