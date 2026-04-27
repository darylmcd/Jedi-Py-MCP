"""Shared helpers and protocols for refactoring submodules."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from python_refactor_mcp.models import (
    Diagnostic,
    InlayHint,
    Position,
    PrepareRenameResult,
    Range,
    RefactorResult,
    SignatureOperation,
    TextEdit,
)
from python_refactor_mcp.util.diff import apply_text_edits, write_atomic
from python_refactor_mcp.util.paths import uri_to_path
from python_refactor_mcp.util.shared import (
    DiagnosticsNotifier,
    attach_post_apply_diagnostics,
)


class PyrightRefactoringBackend(DiagnosticsNotifier, Protocol):
    """Protocol describing Pyright methods used in apply validation paths."""

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

    async def get_inlay_hints(
        self,
        file_path: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
    ) -> list[InlayHint]:
        """Return inlay hints for a source range."""
        ...


class RopeRefactoringBackend(Protocol):
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
        similar: bool,
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

    async def change_signature(
        self,
        file_path: str,
        line: int,
        character: int,
        operations: list[SignatureOperation],
        apply: bool,
    ) -> RefactorResult:
        """Apply signature operation list and update call sites."""
        ...

    async def restructure(
        self,
        pattern: str,
        goal: str,
        checks: dict[str, str] | None,
        imports: list[str] | None,
        file_path: str | None,
        apply: bool,
    ) -> RefactorResult:
        """Apply structural replace patterns to matching code."""
        ...

    async def use_function(
        self,
        file_path: str,
        line: int,
        character: int,
        apply: bool,
    ) -> RefactorResult:
        """Replace duplicate code with calls to selected function."""
        ...

    async def introduce_factory(
        self,
        file_path: str,
        line: int,
        character: int,
        factory_name: str | None,
        global_factory: bool,
        apply: bool,
    ) -> RefactorResult:
        """Introduce a factory function for a class constructor."""
        ...

    async def module_to_package(self, file_path: str, apply: bool) -> RefactorResult:
        """Convert module to package and adjust imports."""
        ...

    async def local_to_field(
        self,
        file_path: str,
        line: int,
        character: int,
        apply: bool,
    ) -> RefactorResult:
        """Promote a local variable to class field."""
        ...

    async def method_object(
        self,
        file_path: str,
        line: int,
        character: int,
        classname: str | None,
        apply: bool,
    ) -> RefactorResult:
        """Extract method logic into a method object class."""
        ...

    async def inline_method(
        self, file_path: str, line: int, character: int, apply: bool,
    ) -> RefactorResult:
        """Inline a method body into all call sites."""
        ...

    async def inline_parameter(
        self, file_path: str, line: int, character: int, apply: bool,
    ) -> RefactorResult:
        """Inline a parameter's default value into the function body."""
        ...

    async def move_method(
        self, file_path: str, line: int, character: int, destination_attr: str, apply: bool,
    ) -> RefactorResult:
        """Move a method between classes via destination attribute."""
        ...

    async def move_module(
        self, source_path: str, destination_package: str, apply: bool,
    ) -> RefactorResult:
        """Move/rename a module or package."""
        ...

    async def generate_code(
        self, file_path: str, line: int, character: int, kind: str, apply: bool,
    ) -> RefactorResult:
        """Generate a missing definition from a usage site."""
        ...

    async def fix_module_names(self, apply: bool) -> RefactorResult:
        """Batch-rename modules to PEP 8 lowercase convention."""
        ...

    async def expand_star_imports(self, file_path: str, apply: bool) -> RefactorResult:
        """Replace star imports with explicit named imports."""
        ...

    async def relatives_to_absolutes(self, file_path: str, apply: bool) -> RefactorResult:
        """Convert relative imports to absolute imports."""
        ...

    async def froms_to_imports(self, file_path: str, apply: bool) -> RefactorResult:
        """Convert from-imports to import statements."""
        ...

    async def handle_long_imports(self, file_path: str, apply: bool) -> RefactorResult:
        """Break long import lines."""
        ...

    async def autoimport_search(self, name: str) -> list[tuple[str, str]]:
        """Search for importable names using AutoImport cache."""
        ...


def range_contains_position(range_value: Range, line: int, character: int) -> bool:
    """Return whether a 0-based position is inside a diagnostic range."""
    start = (range_value.start.line, range_value.start.character)
    end = (range_value.end.line, range_value.end.character)
    target = (line, character)
    return start <= target <= end


def full_file_range(file_path: str) -> Range:
    """Build a range covering the entire current file content."""
    from python_refactor_mcp.errors import RopeError  # noqa: PLC0415
    from python_refactor_mcp.util.shared import end_position_for_content  # noqa: PLC0415

    try:
        content = Path(file_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise RopeError(f"Cannot read file for range computation: {exc}") from exc
    return Range(start=Position(line=0, character=0), end=end_position_for_content(content))


def workspace_edit_to_text_edits(workspace_edit: object) -> list[TextEdit]:
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


def result_from_text_edits(edits: list[TextEdit], description: str, apply: bool) -> RefactorResult:
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


async def post_apply_diagnostics(
    pyright: PyrightRefactoringBackend,
    result: RefactorResult,
) -> RefactorResult:
    """Notify Pyright of changed files and append refreshed diagnostics."""
    return await attach_post_apply_diagnostics(pyright, result)  # type: ignore[return-value]
