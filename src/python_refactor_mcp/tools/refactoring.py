"""Refactoring tools orchestrating rope edits with Pyright validation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from python_refactor_mcp.backends.pyright_lsp import uri_to_path
from python_refactor_mcp.models import Diagnostic, Position, PrepareRenameResult, Range, RefactorResult, TextEdit
from python_refactor_mcp.util.diff import apply_text_edits, write_atomic


class _PyrightRefactoringBackend(Protocol):
    """Protocol describing Pyright methods used in apply validation paths."""

    async def notify_file_changed(self, file_path: str) -> None:
        """Notify backend that file contents changed on disk."""
        ...

    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]:
        """Return diagnostics for one file or the full workspace."""
        ...

    async def get_code_actions(
        self,
        file_path: str,
        range_value: Range,
        diagnostics: list[Diagnostic],
    ) -> list[dict[str, object]]:
        """Return code actions for a range."""
        ...

    async def prepare_rename(self, file_path: str, line: int, char: int) -> PrepareRenameResult | None:
        """Return rename preflight metadata for a source position."""
        ...


class _RopeRefactoringBackend(Protocol):
    """Protocol describing rope refactoring methods used by this module."""

    async def rename(
        self,
        file_path: str,
        line: int,
        character: int,
        new_name: str,
        apply: bool,
    ) -> RefactorResult:
        """Rename symbol and return computed edits/result."""
        ...

    async def extract_method(
        self,
        file_path: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        method_name: str,
        apply: bool,
    ) -> RefactorResult:
        """Extract selected code into a method."""
        ...

    async def extract_variable(
        self,
        file_path: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        variable_name: str,
        apply: bool,
    ) -> RefactorResult:
        """Extract selected code into a variable."""
        ...

    async def inline(self, file_path: str, line: int, character: int, apply: bool) -> RefactorResult:
        """Inline symbol and return computed edits/result."""
        ...

    async def move(
        self,
        source_file: str,
        symbol_name: str,
        destination_file: str,
        apply: bool,
    ) -> RefactorResult:
        """Move symbol and return computed edits/result."""
        ...

    async def introduce_parameter(
        self,
        file_path: str,
        line: int,
        character: int,
        parameter_name: str,
        default_value: str,
        apply: bool,
    ) -> RefactorResult:
        """Introduce a new parameter on a function and update call sites."""
        ...

    async def encapsulate_field(
        self,
        file_path: str,
        line: int,
        character: int,
        apply: bool,
    ) -> RefactorResult:
        """Encapsulate a field using property accessors."""
        ...


def _diagnostic_key(item: Diagnostic) -> tuple[str, int, int, int, int, str, str]:
    """Build a stable key for diagnostic deduplication and ordering."""
    return (
        item.file_path,
        item.range.start.line,
        item.range.start.character,
        item.range.end.line,
        item.range.end.character,
        item.severity,
        item.message,
    )


def _range_contains_position(range_value: Range, line: int, character: int) -> bool:
    """Return whether a 0-based position is inside a diagnostic range."""
    start = (range_value.start.line, range_value.start.character)
    end = (range_value.end.line, range_value.end.character)
    target = (line, character)
    return start <= target <= end


def _end_position_for_content(content: str) -> Position:
    """Compute the end position for a file content string."""
    if not content:
        return Position(line=0, character=0)
    lines = content.splitlines()
    if not lines:
        return Position(line=0, character=0)
    if content.endswith(("\n", "\r")):
        return Position(line=len(lines), character=0)
    return Position(line=len(lines) - 1, character=len(lines[-1]))


def _full_file_range(file_path: str) -> Range:
    """Build a range covering the entire current file content."""
    content = Path(file_path).read_text(encoding="utf-8")
    return Range(start=Position(line=0, character=0), end=_end_position_for_content(content))


def _workspace_edit_to_text_edits(workspace_edit: object) -> list[TextEdit]:
    """Convert an LSP workspace edit payload into project TextEdit models."""
    if not isinstance(workspace_edit, dict):
        return []

    edits: list[TextEdit] = []
    changes = workspace_edit.get("changes")
    if isinstance(changes, dict):
        for uri, file_edits in changes.items():
            if not isinstance(uri, str) or not isinstance(file_edits, list):
                continue
            file_path = uri_to_path(uri)
            for edit in file_edits:
                if not isinstance(edit, dict):
                    continue
                range_value = edit.get("range")
                new_text = edit.get("newText")
                if not isinstance(range_value, dict) or not isinstance(new_text, str):
                    continue
                edits.append(TextEdit(file_path=file_path, range=Range.model_validate(range_value), new_text=new_text))

    document_changes = workspace_edit.get("documentChanges")
    if isinstance(document_changes, list):
        for change in document_changes:
            if not isinstance(change, dict):
                continue
            text_document = change.get("textDocument")
            edits_value = change.get("edits")
            if not isinstance(text_document, dict) or not isinstance(edits_value, list):
                continue
            uri = text_document.get("uri")
            if not isinstance(uri, str):
                continue
            file_path = uri_to_path(uri)
            for edit in edits_value:
                if not isinstance(edit, dict):
                    continue
                range_value = edit.get("range")
                new_text = edit.get("newText")
                if not isinstance(range_value, dict) or not isinstance(new_text, str):
                    continue
                edits.append(TextEdit(file_path=file_path, range=Range.model_validate(range_value), new_text=new_text))

    deduped: dict[tuple[str, int, int, int, int, str], TextEdit] = {}
    for edit in edits:
        key = (
            edit.file_path,
            edit.range.start.line,
            edit.range.start.character,
            edit.range.end.line,
            edit.range.end.character,
            edit.new_text,
        )
        deduped[key] = edit
    return sorted(
        deduped.values(),
        key=lambda item: (
            item.file_path,
            item.range.start.line,
            item.range.start.character,
            item.range.end.line,
            item.range.end.character,
        ),
    )


def _result_from_text_edits(edits: list[TextEdit], description: str, apply: bool) -> RefactorResult:
    """Build a refactor result from LSP-style text edits and optionally apply them."""
    files_affected = sorted({edit.file_path for edit in edits})
    if not apply:
        return RefactorResult(edits=edits, files_affected=files_affected, description=description, applied=False)

    edits_by_file: dict[str, list[TextEdit]] = {}
    for edit in edits:
        edits_by_file.setdefault(edit.file_path, []).append(edit)
    for file_path, file_edits in edits_by_file.items():
        updated = apply_text_edits(file_path, file_edits)
        write_atomic(file_path, updated)

    return RefactorResult(edits=edits, files_affected=files_affected, description=description, applied=True)


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


async def _attach_post_apply_diagnostics(
    pyright: _PyrightRefactoringBackend,
    result: RefactorResult,
) -> RefactorResult:
    """Notify Pyright of changed files and append refreshed diagnostics."""
    if not result.applied:
        return result

    normalized_files = sorted({file_path for file_path in result.files_affected})
    for file_path in normalized_files:
        await pyright.notify_file_changed(file_path)

    diagnostics: dict[tuple[str, int, int, int, int, str, str], Diagnostic] = {}
    for file_path in normalized_files:
        file_diagnostics = await pyright.get_diagnostics(file_path)
        for diagnostic in file_diagnostics:
            diagnostics[_diagnostic_key(diagnostic)] = diagnostic

    result.diagnostics_after = sorted(diagnostics.values(), key=_diagnostic_key)
    return result


async def rename_symbol(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    new_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Rename a symbol at the provided position."""
    result = await rope.rename(file_path, line, character, new_name, apply)
    return await _attach_post_apply_diagnostics(pyright, result)


async def extract_method(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    start_line: int,
    start_character: int,
    end_line: int,
    end_character: int,
    method_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Extract selected code into a method."""
    result = await rope.extract_method(
        file_path,
        start_line,
        start_character,
        end_line,
        end_character,
        method_name,
        apply,
    )
    return await _attach_post_apply_diagnostics(pyright, result)


async def extract_variable(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    start_line: int,
    start_character: int,
    end_line: int,
    end_character: int,
    variable_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Extract selected expression into a variable."""
    result = await rope.extract_variable(
        file_path,
        start_line,
        start_character,
        end_line,
        end_character,
        variable_name,
        apply,
    )
    return await _attach_post_apply_diagnostics(pyright, result)


async def inline_variable(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Inline a variable at the provided position."""
    result = await rope.inline(file_path, line, character, apply)
    return await _attach_post_apply_diagnostics(pyright, result)


async def move_symbol(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    source_file: str,
    symbol_name: str,
    destination_file: str,
    apply: bool = False,
) -> RefactorResult:
    """Move a symbol from one file to another."""
    result = await rope.move(source_file, symbol_name, destination_file, apply)
    return await _attach_post_apply_diagnostics(pyright, result)


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
    selected = _pick_code_action(organize_actions, "organize imports")
    edits = _workspace_edit_to_text_edits(selected.get("edit"))
    if not edits:
        raise ValueError("Organize imports did not return editable workspace changes.")
    result = _result_from_text_edits(edits, "Organized imports", apply)
    return await _attach_post_apply_diagnostics(pyright, result)


async def prepare_rename(
    pyright: _PyrightRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
) -> PrepareRenameResult | None:
    """Run rename preflight checks for the requested source position."""
    return await pyright.prepare_rename(file_path, line, character)


async def introduce_parameter(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    parameter_name: str,
    default_value: str,
    apply: bool = False,
) -> RefactorResult:
    """Introduce a parameter and optionally apply edits on disk."""
    result = await rope.introduce_parameter(
        file_path,
        line,
        character,
        parameter_name,
        default_value,
        apply,
    )
    return await _attach_post_apply_diagnostics(pyright, result)


async def encapsulate_field(
    pyright: _PyrightRefactoringBackend,
    rope: _RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Encapsulate a field into property accessors and optionally apply changes."""
    result = await rope.encapsulate_field(file_path, line, character, apply)
    return await _attach_post_apply_diagnostics(pyright, result)
