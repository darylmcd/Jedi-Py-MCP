"""rope backend implementation for mutation-oriented refactoring operations."""

from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path
from typing import Protocol, cast

from rope.base.change import ChangeContents, ChangeSet  # type: ignore[import-untyped]
from rope.base.project import Project  # type: ignore[import-untyped]
from rope.base.resources import Resource  # type: ignore[import-untyped]
from rope.refactor.extract import ExtractMethod, ExtractVariable  # type: ignore[import-untyped]
from rope.refactor.inline import create_inline  # type: ignore[import-untyped]
from rope.refactor.move import create_move  # type: ignore[import-untyped]
from rope.refactor.rename import Rename  # type: ignore[import-untyped]

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import RopeError
from python_refactor_mcp.models import Position, Range, RefactorResult, TextEdit
from python_refactor_mcp.util.diff import apply_text_edits, write_atomic

_LOGGER = logging.getLogger(__name__)


class _MoveRefactoring(Protocol):
    """Protocol for rope move refactoring instances with dynamic runtime type."""

    def get_changes(self, dest: object, resources: object | None = None) -> ChangeSet:
        """Return rope change set for move operation."""
        ...


def _absolute_path(path: str) -> str:
    """Return normalized absolute path string."""
    return str(Path(path).resolve())


def _end_position_for_content(content: str) -> Position:
    """Compute the end position of an entire file content string."""
    if not content:
        return Position(line=0, character=0)
    lines = content.splitlines()
    if not lines:
        return Position(line=0, character=0)
    if content.endswith(("\n", "\r")):
        return Position(line=len(lines), character=0)
    return Position(line=len(lines) - 1, character=len(lines[-1]))


class RopeBackend:
    """rope refactoring backend used for code edits and apply workflows."""

    def __init__(self, config: ServerConfig) -> None:
        """Initialize backend config and deferred rope project state."""
        self._config = config
        self._project: Project | None = None

    def initialize(self) -> None:
        """Create rope project for the configured workspace root."""
        self._project = Project(str(self._config.workspace_root))

    def close(self) -> None:
        """Close rope project resources if initialized."""
        if self._project is not None:
            self._project.close()
            self._project = None

    def _require_project(self) -> Project:
        """Return initialized rope project or raise backend error."""
        if self._project is None:
            raise RopeError("rope backend is not initialized.")
        return self._project

    def _resource_for_path(self, file_path: str) -> Resource:
        """Resolve a rope resource from an absolute file path."""
        project = self._require_project()
        absolute = Path(file_path).resolve()
        try:
            relative = absolute.relative_to(self._config.workspace_root)
        except ValueError as exc:
            raise RopeError(f"Path is outside workspace root: {absolute}") from exc
        return project.get_resource(str(relative).replace("\\", "/"))

    def _position_to_offset(self, file_path: str, line: int, character: int) -> int:
        """Convert a 0-based line/character position to rope offset."""
        if line < 0 or character < 0:
            raise RopeError("line and character must be non-negative")

        content = Path(file_path).read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        if not lines:
            lines = [""]

        if line >= len(lines):
            if line == len(lines) and character == 0:
                return len(content)
            raise RopeError(f"line out of range: {line}")

        line_text = lines[line].rstrip("\r\n")
        if character > len(line_text):
            raise RopeError(
                f"character out of range for line {line}: {character} > {len(line_text)}"
            )

        return sum(len(chunk) for chunk in lines[:line]) + character

    def _offset_to_position(self, file_path: str, offset: int) -> Position:
        """Convert rope offset to a 0-based line/character position."""
        if offset < 0:
            raise RopeError("offset must be non-negative")

        content = Path(file_path).read_text(encoding="utf-8")
        if offset > len(content):
            raise RopeError(f"offset out of range: {offset}")

        prefix = content[:offset]
        line = prefix.count("\n")
        if line == 0:
            return Position(line=0, character=len(prefix))

        last_newline = prefix.rfind("\n")
        return Position(line=line, character=len(prefix) - last_newline - 1)

    def _changes_to_edits(self, changes: ChangeSet) -> list[TextEdit]:
        """Convert rope changes into full-file replacement text edits."""
        edits: list[TextEdit] = []
        for change in changes.changes:
            if not isinstance(change, ChangeContents):
                continue
            absolute_file = _absolute_path(str(self._config.workspace_root / change.resource.path))
            old_content = Path(absolute_file).read_text(encoding="utf-8")
            end = _end_position_for_content(old_content)
            edits.append(
                TextEdit(
                    file_path=absolute_file,
                    range=Range(
                        start=Position(line=0, character=0),
                        end=end,
                    ),
                    new_text=change.new_contents,
                )
            )
        return edits

    def _apply_changes(self, changes: ChangeSet) -> list[str]:
        """Apply rope changes to disk atomically and return changed absolute files."""
        edits = self._changes_to_edits(changes)
        changed_files: list[str] = []
        for edit in edits:
            new_content = apply_text_edits(edit.file_path, [edit])
            write_atomic(edit.file_path, new_content)
            changed_files.append(edit.file_path)
        return changed_files

    def _build_result(self, changes: ChangeSet, description: str, apply: bool) -> RefactorResult:
        """Build a model result from rope changes and apply mode."""
        edits = self._changes_to_edits(changes)
        if apply:
            files_affected = self._apply_changes(changes)
            return RefactorResult(
                edits=edits,
                files_affected=files_affected,
                description=description,
                applied=True,
            )

        files = sorted({edit.file_path for edit in edits})
        return RefactorResult(edits=edits, files_affected=files, description=description, applied=False)

    def _find_symbol_offset(self, source_file: str, symbol_name: str) -> int:
        """Find the source offset for a module-level symbol definition by name."""
        content = Path(source_file).read_text(encoding="utf-8")
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            raise RopeError(f"Failed to parse source for symbol lookup: {source_file}") from exc

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol_name:
                return self._position_to_offset(source_file, node.lineno - 1, node.col_offset)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == symbol_name:
                        return self._position_to_offset(source_file, target.lineno - 1, target.col_offset)

        marker = f"{symbol_name}"
        index = content.find(marker)
        if index >= 0:
            return index
        raise RopeError(f"Unable to locate symbol '{symbol_name}' in {source_file}")

    async def rename(
        self,
        file_path: str,
        line: int,
        character: int,
        new_name: str,
        apply: bool,
    ) -> RefactorResult:
        """Rename a symbol using rope and optionally apply resulting edits."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            changes = Rename(project, resource, offset).get_changes(new_name)
            return self._build_result(changes, f"Renamed symbol to '{new_name}'", apply)

        try:
            result = await asyncio.to_thread(_work)
            _LOGGER.debug("rope rename produced %d edits", len(result.edits))
            return result
        except Exception as exc:
            raise RopeError(f"rope rename failed for {file_path}:{line}:{character}") from exc

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
        """Extract selected code into a new method and optionally apply edits."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            start = self._position_to_offset(file_path, start_line, start_character)
            end = self._position_to_offset(file_path, end_line, end_character)
            changes = ExtractMethod(project, resource, start, end).get_changes(method_name)
            return self._build_result(changes, f"Extracted method '{method_name}'", apply)

        try:
            result = await asyncio.to_thread(_work)
            _LOGGER.debug("rope extract_method produced %d edits", len(result.edits))
            return result
        except Exception as exc:
            raise RopeError(f"rope extract_method failed for {file_path}") from exc

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
        """Extract selected expression into a variable and optionally apply edits."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            start = self._position_to_offset(file_path, start_line, start_character)
            end = self._position_to_offset(file_path, end_line, end_character)
            changes = ExtractVariable(project, resource, start, end).get_changes(variable_name)
            return self._build_result(changes, f"Extracted variable '{variable_name}'", apply)

        try:
            result = await asyncio.to_thread(_work)
            _LOGGER.debug("rope extract_variable produced %d edits", len(result.edits))
            return result
        except Exception as exc:
            raise RopeError(f"rope extract_variable failed for {file_path}") from exc

    async def inline(self, file_path: str, line: int, character: int, apply: bool) -> RefactorResult:
        """Inline a symbol and optionally apply edits."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            changes = create_inline(project, resource, offset).get_changes()
            return self._build_result(changes, "Inlined symbol", apply)

        try:
            result = await asyncio.to_thread(_work)
            _LOGGER.debug("rope inline produced %d edits", len(result.edits))
            return result
        except Exception as exc:
            raise RopeError(f"rope inline failed for {file_path}:{line}:{character}") from exc

    async def move(
        self,
        source_file: str,
        symbol_name: str,
        destination_file: str,
        apply: bool,
    ) -> RefactorResult:
        """Move a symbol to a destination module and optionally apply edits."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            source_resource = self._resource_for_path(source_file)
            destination_resource = self._resource_for_path(destination_file)
            offset = self._find_symbol_offset(source_file, symbol_name)
            mover = cast(_MoveRefactoring, create_move(project, source_resource, offset))
            changes = mover.get_changes(destination_resource)
            return self._build_result(
                changes,
                f"Moved symbol '{symbol_name}' to {destination_file}",
                apply,
            )

        try:
            result = await asyncio.to_thread(_work)
            _LOGGER.debug("rope move produced %d edits", len(result.edits))
            return result
        except Exception as exc:
            raise RopeError(f"rope move failed for symbol {symbol_name}") from exc
