"""Code action and import organization tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from python_refactor_mcp.errors import ToolInputError
from python_refactor_mcp.models import CodeActionResult, Position, Range, RefactorResult, TextEdit

from .helpers import (
    full_file_range,
    post_apply_diagnostics,
    range_contains_position,
    result_from_text_edits,
    workspace_edit_to_text_edits,
)

if TYPE_CHECKING:
    from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient


def _action_titles(actions: list[dict[str, object]]) -> list[str]:
    """Return the string titles of *actions*, in the order Pyright offered them."""
    return [title for action in actions if isinstance(title := action.get("title"), str)]


def _pick_code_action(actions: list[dict[str, object]], action_title: str) -> dict[str, object]:
    """Select the code action whose title matches *action_title*.

    An exact case-insensitive match wins over a substring match. Raises
    ``ToolInputError`` naming the available titles when nothing matches.
    """
    lowered_title = action_title.strip().lower()
    for action in actions:
        title = action.get("title")
        if isinstance(title, str) and title.strip().lower() == lowered_title:
            return action
    for action in actions:
        title = action.get("title")
        if isinstance(title, str) and lowered_title in title.strip().lower():
            return action
    available = _action_titles(actions)
    raise ToolInputError(
        f"No code action matches action_title '{action_title}'. "
        f"Available titles: {', '.join(repr(title) for title in available) or 'none'}."
    )


async def apply_code_action(
    pyright: PyrightLSPClient,
    file_path: str,
    line: int,
    character: int,
    action_title: str | None = None,
    apply: bool = False,
) -> CodeActionResult:
    """Preview or apply a Pyright code action at a source position.

    With ``action_title`` omitted, return the offered titles in
    ``available_actions`` without previewing or applying anything, even when
    ``apply=True``.
    """
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
    if not actions:
        return CodeActionResult(
            edits=[],
            files_affected=[],
            description="No code actions available at the requested position",
            applied=False,
            available_actions=[],
        )
    titles = _action_titles(actions)
    if action_title is None:
        return CodeActionResult(
            edits=[],
            files_affected=[],
            description=f"{len(titles)} code action(s) available; pass action_title to preview or apply one",
            applied=False,
            available_actions=titles,
        )
    selected = _pick_code_action(actions, action_title)
    title = selected.get("title")
    description = title if isinstance(title, str) and title else "Applied code action"
    edits = workspace_edit_to_text_edits(selected.get("edit"))
    if not edits:
        raise ToolInputError(
            f"Code action '{description}' does not provide editable workspace changes; "
            "choose a different action_title."
        )
    result = await post_apply_diagnostics(pyright, result_from_text_edits(edits, description, apply))
    return CodeActionResult.model_validate({**result.model_dump(), "available_actions": titles})


async def organize_imports(
    pyright: PyrightLSPClient,
    file_path: str,
    apply: bool = False,
    file_paths: list[str] | None = None,
) -> RefactorResult:
    """Run organize imports for one or multiple files using Pyright code actions."""
    targets = file_paths if file_paths is not None else [file_path]
    all_edits: list[TextEdit] = []
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
