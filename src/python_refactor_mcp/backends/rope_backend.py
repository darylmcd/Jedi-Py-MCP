"""rope backend implementation for mutation-oriented refactoring operations."""

from __future__ import annotations

import ast
import asyncio
import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from rope.base.change import ChangeContents, ChangeSet  # type: ignore[import-untyped]
from rope.base.project import Project  # type: ignore[import-untyped]
from rope.base.resources import Resource  # type: ignore[import-untyped]
from rope.contrib import generate as rope_generate  # type: ignore[import-untyped]
from rope.contrib.autoimport.sqlite import AutoImport  # type: ignore[import-untyped]
from rope.contrib.finderrors import find_errors as _rope_find_errors  # type: ignore[import-untyped]
from rope.contrib.fixmodnames import FixModuleNames  # type: ignore[import-untyped]
from rope.refactor.change_signature import (  # type: ignore[import-untyped]
    ArgumentAdder,
    ArgumentDefaultInliner,
    ArgumentNormalizer,
    ArgumentRemover,
    ArgumentReorderer,
    ChangeSignature,
)
from rope.refactor.encapsulate_field import EncapsulateField  # type: ignore[import-untyped]
from rope.refactor.extract import ExtractMethod, ExtractVariable  # type: ignore[import-untyped]
from rope.refactor.importutils import ImportOrganizer  # type: ignore[import-untyped]
from rope.refactor.inline import create_inline  # type: ignore[import-untyped]
from rope.refactor.introduce_factory import IntroduceFactory  # type: ignore[import-untyped]
from rope.refactor.introduce_parameter import IntroduceParameter  # type: ignore[import-untyped]
from rope.refactor.localtofield import LocalToField  # type: ignore[import-untyped]
from rope.refactor.method_object import MethodObject  # type: ignore[import-untyped]
from rope.refactor.move import create_move  # type: ignore[import-untyped]
from rope.refactor.rename import Rename  # type: ignore[import-untyped]
from rope.refactor.restructure import Restructure  # type: ignore[import-untyped]
from rope.refactor.topackage import ModuleToPackage  # type: ignore[import-untyped]
from rope.refactor.usefunction import UseFunction  # type: ignore[import-untyped]

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import RopeError
from python_refactor_mcp.models import HistoryEntry, Position, Range, RefactorResult, SignatureOperation, TextEdit
from python_refactor_mcp.util.diff import apply_text_edits, write_atomic
from python_refactor_mcp.util.shared import end_position_for_content as _end_position_for_content
from python_refactor_mcp.util.timing import timed

_LOGGER = logging.getLogger(__name__)
_DEFAULT_ROPE_TIMEOUT = 30.0


def _absolute_path(path: str) -> str:
    """Return normalized absolute path string."""
    return str(Path(path).resolve())


def _build_add(op: SignatureOperation) -> list[object]:
    if op.index is None or not op.name:
        raise RopeError("change_signature add operation requires index and name")
    return [ArgumentAdder(op.index, op.name, default=op.default)]


def _build_remove(op: SignatureOperation) -> list[object]:
    if op.index is None:
        raise RopeError("change_signature remove operation requires index")
    return [ArgumentRemover(op.index)]


def _build_reorder(op: SignatureOperation) -> list[object]:
    if not op.new_order:
        raise RopeError("change_signature reorder operation requires new_order")
    return [ArgumentReorderer(op.new_order)]


def _build_inline_default(op: SignatureOperation) -> list[object]:
    if op.index is None:
        raise RopeError("change_signature inline_default operation requires index")
    return [ArgumentDefaultInliner(op.index)]


def _build_normalize(op: SignatureOperation) -> list[object]:
    return [ArgumentNormalizer()]


def _build_rename(op: SignatureOperation) -> list[object]:
    if op.index is None or not op.new_name:
        raise RopeError("change_signature rename operation requires index and new_name")
    return [ArgumentRemover(op.index), ArgumentAdder(op.index, op.new_name, default=op.default)]


_OP_DISPATCH: dict[str, Callable[[SignatureOperation], list[object]]] = {
    "add": _build_add,
    "remove": _build_remove,
    "reorder": _build_reorder,
    "inline_default": _build_inline_default,
    "normalize": _build_normalize,
    "rename": _build_rename,
}


def _build_signature_changers(operations: list[SignatureOperation]) -> list[object]:
    """Map signature operation descriptors to rope changer objects."""
    changers: list[object] = []
    for operation in operations:
        builder = _OP_DISPATCH.get(operation.op.strip().lower())
        if builder is None:
            raise RopeError(f"Unsupported change_signature operation: {operation.op}")
        changers.extend(builder(operation))
    return changers


class RopeBackend:
    """rope refactoring backend used for code edits and apply workflows."""

    def __init__(self, config: ServerConfig) -> None:
        """Initialize backend config and deferred rope project state."""
        self._config = config
        self._project: Project | None = None
        raw = os.environ.get("ROPE_OPERATION_TIMEOUT_SECONDS", "")
        try:
            self._timeout = max(float(raw), 1.0) if raw else _DEFAULT_ROPE_TIMEOUT
        except ValueError:
            self._timeout = _DEFAULT_ROPE_TIMEOUT

    def initialize(self) -> None:
        """Create rope project for the configured workspace root."""
        self._project = Project(
            str(self._config.workspace_root),
            **cast(Any, self._config.rope_prefs),
        )
        # Pre-warm the AutoImport cache so autoimport_search returns results immediately.
        try:
            with AutoImport(self._project) as ai:  # pyright: ignore[reportGeneralTypeIssues]
                ai.generate_cache()
        except Exception:
            _LOGGER.debug("AutoImport cache pre-warm failed", exc_info=True)

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
            raise RopeError(f"Path is outside workspace root: {absolute}: {exc}") from exc
        # Rope expects forward-slash paths internally regardless of OS.
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

    def _apply_edits(self, edits: list[TextEdit]) -> list[str]:
        """Apply pre-computed text edits to disk with rollback on failure."""
        # Capture originals for rollback.
        originals: dict[str, str] = {}
        for edit in edits:
            if edit.file_path not in originals:
                originals[edit.file_path] = Path(edit.file_path).read_text(encoding="utf-8")

        changed_files: list[str] = []
        try:
            for edit in edits:
                new_content = apply_text_edits(edit.file_path, [edit])
                write_atomic(edit.file_path, new_content)
                changed_files.append(edit.file_path)
        except Exception:
            # Rollback already-written files on any failure.
            for path in changed_files:
                if path in originals:
                    write_atomic(path, originals[path])
            raise
        return changed_files

    def _build_result(self, changes: ChangeSet | None, description: str, apply: bool) -> RefactorResult:
        """Build a model result from rope changes and apply mode."""
        if changes is None:
            return RefactorResult(edits=[], files_affected=[], description=description, applied=False)
        edits = self._changes_to_edits(changes)
        if apply:
            files_affected = self._apply_edits(edits)
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
            raise RopeError(f"Failed to parse source for symbol lookup: {source_file}: {exc}") from exc

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol_name:
                return self._position_to_offset(source_file, node.lineno - 1, node.col_offset)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == symbol_name:
                        return self._position_to_offset(source_file, target.lineno - 1, target.col_offset)

        # Fallback: word-boundary match avoids matching substrings (e.g. "foo" inside "foobar").
        match = re.search(r"\b" + re.escape(symbol_name) + r"\b", content)
        if match is not None:
            return match.start()
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
            async with timed(_LOGGER, "rope.rename"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            _LOGGER.debug("rope rename produced %d edits", len(result.edits))
            return result
        except Exception as exc:
            raise RopeError(f"rope rename failed for {file_path}:{line}:{character}: {exc}") from exc

    async def extract_method(
        self,
        file_path: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        method_name: str,
        similar: bool = False,
        apply: bool = False,
    ) -> RefactorResult:
        """Extract selected code into a new method and optionally apply edits."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            start = self._position_to_offset(file_path, start_line, start_character)
            end = self._position_to_offset(file_path, end_line, end_character)
            changes = ExtractMethod(project, resource, start, end).get_changes(method_name, similar=similar)
            return self._build_result(changes, f"Extracted method '{method_name}'", apply)

        try:
            async with timed(_LOGGER, "rope.extract_method"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope extract_method failed for {file_path}: {exc}") from exc

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
            async with timed(_LOGGER, "rope.extract_variable"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope extract_variable failed for {file_path}: {exc}") from exc

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
            async with timed(_LOGGER, "rope.inline"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope inline failed for {file_path}:{line}:{character}: {exc}") from exc

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
            mover = create_move(project, source_resource, offset)
            changes = mover.get_changes(cast(Any, destination_resource))
            return self._build_result(
                changes,
                f"Moved symbol '{symbol_name}' to {destination_file}",
                apply,
            )

        try:
            async with timed(_LOGGER, "rope.move"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope move failed for symbol {symbol_name}: {exc}") from exc

    async def introduce_parameter(
        self,
        file_path: str,
        line: int,
        character: int,
        parameter_name: str,
        default_value: str,
        apply: bool,
    ) -> RefactorResult:
        """Introduce a parameter and optionally apply resulting edits."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            parameter_spec = parameter_name.strip()
            if default_value.strip():
                parameter_spec = f"{parameter_spec}={default_value.strip()}"
            changes = IntroduceParameter(project, resource, offset).get_changes(parameter_spec)
            return self._build_result(
                changes,
                f"Introduced parameter '{parameter_name}'",
                apply,
            )

        try:
            async with timed(_LOGGER, "rope.introduce_parameter"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(
                f"rope introduce_parameter failed for {file_path}:{line}:{character}"
            ) from exc

    async def encapsulate_field(
        self,
        file_path: str,
        line: int,
        character: int,
        apply: bool,
    ) -> RefactorResult:
        """Encapsulate a field and optionally apply resulting edits."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            changes = EncapsulateField(project, resource, offset).get_changes()
            return self._build_result(changes, "Encapsulated field", apply)

        try:
            async with timed(_LOGGER, "rope.encapsulate_field"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope encapsulate_field failed for {file_path}:{line}:{character}: {exc}") from exc

    async def change_signature(
        self,
        file_path: str,
        line: int,
        character: int,
        operations: list[SignatureOperation],
        apply: bool,
    ) -> RefactorResult:
        """Apply ordered signature changes to a function and call sites.

        .. note::

            Rope's ``ArgumentNormalizer`` and ``ArgumentAdder`` do **not**
            preserve Python 3 type annotations on modified parameters.
            The ``normalize`` operation and ``rename`` (remove + re-add)
            may strip annotations.  This is a known upstream rope limitation.
        """

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)

            changers = _build_signature_changers(operations)
            changes = ChangeSignature(project, resource, offset).get_changes(changers)
            return self._build_result(changes, "Changed function signature", apply)

        try:
            async with timed(_LOGGER, "rope.change_signature"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope change_signature failed for {file_path}:{line}:{character}: {exc}") from exc

    async def restructure(
        self,
        pattern: str,
        goal: str,
        checks: dict[str, str] | None,
        imports: list[str] | None,
        file_path: str | None,
        apply: bool,
    ) -> RefactorResult:
        """Apply rope restructure pattern replacement and return resulting edits."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resources: list[Resource] | None = None
            if file_path is not None:
                resources = [self._resource_for_path(file_path)]
            refactor = Restructure(project, pattern, goal)
            changes = refactor.get_changes(checks=checks, imports=imports, resources=resources)
            return self._build_result(changes, "Applied structural replacement", apply)

        try:
            async with timed(_LOGGER, "rope.restructure"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError("rope restructure failed: {exc}") from exc

    async def use_function(
        self,
        file_path: str,
        line: int,
        character: int,
        apply: bool,
    ) -> RefactorResult:
        """Replace duplicated code segments with calls to selected function."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            changes = UseFunction(project, resource, offset).get_changes()
            return self._build_result(changes, "Replaced duplicated code with function call", apply)

        try:
            async with timed(_LOGGER, "rope.use_function"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope use_function failed for {file_path}:{line}:{character}: {exc}") from exc

    async def introduce_factory(
        self,
        file_path: str,
        line: int,
        character: int,
        factory_name: str | None,
        global_factory: bool,
        apply: bool,
    ) -> RefactorResult:
        """Introduce a factory helper for selected class constructor."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            refactor = IntroduceFactory(project, resource, offset)
            default_name = f"create_{refactor.get_name().lower()}"
            changes = refactor.get_changes(factory_name or default_name, global_factory=global_factory)
            return self._build_result(changes, "Introduced factory", apply)

        try:
            async with timed(_LOGGER, "rope.introduce_factory"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope introduce_factory failed for {file_path}:{line}:{character}: {exc}") from exc

    async def module_to_package(self, file_path: str, apply: bool) -> RefactorResult:
        """Convert a module into a package preserving public imports."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            changes = ModuleToPackage(project, resource).get_changes()
            return self._build_result(changes, "Converted module to package", apply)

        try:
            async with timed(_LOGGER, "rope.module_to_package"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope module_to_package failed for {file_path}: {exc}") from exc

    async def local_to_field(
        self,
        file_path: str,
        line: int,
        character: int,
        apply: bool,
    ) -> RefactorResult:
        """Promote local variable usage to instance field."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            changes = LocalToField(project, resource, offset).get_changes()
            return self._build_result(changes, "Promoted local to field", apply)

        try:
            async with timed(_LOGGER, "rope.local_to_field"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope local_to_field failed for {file_path}:{line}:{character}: {exc}") from exc

    async def method_object(
        self,
        file_path: str,
        line: int,
        character: int,
        classname: str | None,
        apply: bool,
    ) -> RefactorResult:
        """Extract selected method logic to a new method-object class."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            changes = MethodObject(project, resource, offset).get_changes(classname=classname)
            return self._build_result(changes, "Extracted method object", apply)

        try:
            async with timed(_LOGGER, "rope.method_object"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope method_object failed for {file_path}:{line}:{character}: {exc}") from exc

    async def inline_method(
        self,
        file_path: str,
        line: int,
        character: int,
        apply: bool,
    ) -> RefactorResult:
        """Inline a method/function body into all call sites and remove the definition."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            changes = create_inline(project, resource, offset).get_changes()
            return self._build_result(changes, "Inlined method", apply)

        try:
            async with timed(_LOGGER, "rope.inline_method"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope inline_method failed for {file_path}:{line}:{character}: {exc}") from exc

    async def inline_parameter(
        self,
        file_path: str,
        line: int,
        character: int,
        apply: bool,
    ) -> RefactorResult:
        """Inline a parameter's default value into the function body and remove it from the signature."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            changes = create_inline(project, resource, offset).get_changes()
            return self._build_result(changes, "Inlined parameter", apply)

        try:
            async with timed(_LOGGER, "rope.inline_parameter"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope inline_parameter failed for {file_path}:{line}:{character}: {exc}") from exc

    async def move_method(
        self,
        file_path: str,
        line: int,
        character: int,
        destination_attr: str,
        apply: bool,
    ) -> RefactorResult:
        """Move a method from one class to another via a destination attribute name."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            mover = create_move(project, resource, offset)
            changes = mover.get_changes(cast(Any, destination_attr))
            return self._build_result(changes, f"Moved method to '{destination_attr}'", apply)

        try:
            async with timed(_LOGGER, "rope.move_method"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope move_method failed for {file_path}:{line}:{character}: {exc}") from exc

    async def move_module(
        self,
        source_path: str,
        destination_package: str,
        apply: bool,
    ) -> RefactorResult:
        """Move/rename a module or package, updating all imports project-wide."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            source_resource = self._resource_for_path(source_path)
            dest_resource = self._resource_for_path(destination_package)
            mover = create_move(project, source_resource, None)
            changes = mover.get_changes(cast(Any, dest_resource))
            return self._build_result(
                changes,
                f"Moved module '{source_path}' to '{destination_package}'",
                apply,
            )

        try:
            async with timed(_LOGGER, "rope.move_module"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope move_module failed for {source_path}: {exc}") from exc

    async def generate_code(
        self,
        file_path: str,
        line: int,
        character: int,
        kind: str,
        apply: bool,
    ) -> RefactorResult:
        """Generate a missing class, function, variable, module, or package from a usage site."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            kind_lower = kind.strip().lower()
            generators: dict[str, Any] = {
                "class": rope_generate.create_class,  # pyright: ignore[reportAttributeAccessIssue]
                "function": rope_generate.create_function,  # pyright: ignore[reportAttributeAccessIssue]
                "variable": rope_generate.create_variable,  # pyright: ignore[reportAttributeAccessIssue]
                "module": rope_generate.create_module,
                "package": rope_generate.create_package,
            }
            creator = generators.get(kind_lower)
            if creator is None:
                raise RopeError(f"Unsupported generation kind: {kind}. Use: {', '.join(generators)}")
            changes = cast(ChangeSet | None, creator(project, resource, offset))
            return self._build_result(changes, f"Generated {kind_lower}", apply)

        try:
            async with timed(_LOGGER, "rope.generate_code"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope generate_code failed for {file_path}:{line}:{character}: {exc}") from exc

    async def fix_module_names(self, apply: bool) -> RefactorResult:
        """Batch-rename modules to conform to PEP 8 lowercase naming."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            fixer = FixModuleNames(project)
            changes = fixer.get_changes()
            return self._build_result(changes, "Fixed module names to PEP 8 convention", apply)

        try:
            async with timed(_LOGGER, "rope.fix_module_names"):
                result = await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
            return result
        except Exception as exc:
            raise RopeError(f"rope fix_module_names failed: {exc}") from exc

    # ── Import organizer methods ──────────────────────────────────────────

    async def expand_star_imports(self, file_path: str, apply: bool) -> RefactorResult:
        """Replace ``from x import *`` with explicit named imports."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            organizer = ImportOrganizer(project)
            changes = organizer.expand_star_imports(resource)
            return self._build_result(changes, "Expanded star imports", apply)

        try:
            async with timed(_LOGGER, "rope.expand_star_imports"):
                return await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
        except Exception as exc:
            raise RopeError(f"rope expand_star_imports failed for {file_path}: {exc}") from exc

    async def relatives_to_absolutes(self, file_path: str, apply: bool) -> RefactorResult:
        """Convert all relative imports to absolute imports."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            organizer = ImportOrganizer(project)
            changes = organizer.relatives_to_absolutes(resource)
            return self._build_result(changes, "Converted relative imports to absolute", apply)

        try:
            async with timed(_LOGGER, "rope.relatives_to_absolutes"):
                return await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
        except Exception as exc:
            raise RopeError(f"rope relatives_to_absolutes failed for {file_path}: {exc}") from exc

    async def froms_to_imports(self, file_path: str, apply: bool) -> RefactorResult:
        """Convert ``from module import name`` to ``import module`` style."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            organizer = ImportOrganizer(project)
            changes = organizer.froms_to_imports(resource)
            return self._build_result(changes, "Converted from-imports to import statements", apply)

        try:
            async with timed(_LOGGER, "rope.froms_to_imports"):
                return await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
        except Exception as exc:
            raise RopeError(f"rope froms_to_imports failed for {file_path}: {exc}") from exc

    async def handle_long_imports(self, file_path: str, apply: bool) -> RefactorResult:
        """Break long import lines per project preferences."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            organizer = ImportOrganizer(project)
            changes = organizer.handle_long_imports(resource)
            return self._build_result(changes, "Handled long imports", apply)

        try:
            async with timed(_LOGGER, "rope.handle_long_imports"):
                return await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
        except Exception as exc:
            raise RopeError(f"rope handle_long_imports failed for {file_path}: {exc}") from exc

    # ── AutoImport cache ──────────────────────────────────────────────────

    async def autoimport_search(self, name: str) -> list[tuple[str, str]]:
        """Search for importable names using rope's AutoImport SQLite cache.

        Returns a list of (name, module) tuples.
        """

        def _work() -> list[tuple[str, str]]:
            project = self._require_project()
            with AutoImport(project) as ai:  # pyright: ignore[reportGeneralTypeIssues]
                try:
                    ai.generate_cache()
                except Exception:
                    _LOGGER.warning("AutoImport cache generation failed; searching existing cache")
                return cast(list[tuple[str, str]], ai.search(name))

        try:
            async with timed(_LOGGER, "rope.autoimport_search"):
                return await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
        except Exception as exc:
            _LOGGER.warning("rope autoimport_search failed for '%s': %s", name, exc, exc_info=True)
            return []

    async def find_errors(self, file_path: str) -> list[dict[str, object]]:
        """Run rope's static analysis for bad name/attribute accesses."""

        def _work() -> list[dict[str, object]]:
            project = self._require_project()
            resource = self._resource_for_path(file_path)
            errors = _rope_find_errors(project, resource)
            results: list[dict[str, object]] = []
            for err in errors:
                lineno = getattr(err, "lineno", None)
                error_msg = getattr(err, "error", str(err))
                results.append({
                    "file_path": str(Path(file_path).resolve()),
                    "line": (lineno - 1) if isinstance(lineno, int) else 0,
                    "message": str(error_msg),
                })
            return results

        try:
            async with timed(_LOGGER, "rope.find_errors"):
                return await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
        except Exception as exc:
            raise RopeError(f"rope find_errors failed for {file_path}: {exc}") from exc

    # ── Undo/Redo History ──

    async def undo(self, count: int = 1) -> RefactorResult:
        """Undo the last *count* refactoring operations."""
        project = self._require_project()

        def _work() -> RefactorResult:
            history = project.history
            for _ in range(count):
                history.undo()
            return RefactorResult(
                edits=[], files_affected=[], description=f"Undid {count} operation(s)", applied=True,
            )

        try:
            async with timed(_LOGGER, "rope.undo"):
                return await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
        except Exception as exc:
            raise RopeError(f"rope undo failed: {exc}") from exc

    async def redo(self, count: int = 1) -> RefactorResult:
        """Redo the last *count* undone refactoring operations."""
        project = self._require_project()

        def _work() -> RefactorResult:
            history = project.history
            for _ in range(count):
                history.redo()
            return RefactorResult(
                edits=[], files_affected=[], description=f"Redid {count} operation(s)", applied=True,
            )

        try:
            async with timed(_LOGGER, "rope.redo"):
                return await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
        except Exception as exc:
            raise RopeError(f"rope redo failed: {exc}") from exc

    async def get_history(self) -> list[HistoryEntry]:
        """Return the refactoring history as a list of HistoryEntry objects."""
        project = self._require_project()

        def _work() -> list[HistoryEntry]:
            history = project.history
            entries: list[HistoryEntry] = []
            for change_set in getattr(history, "undo_list", []):
                description = str(getattr(change_set, "description", change_set))
                date = str(getattr(change_set, "date", ""))
                resources = getattr(change_set, "resources", [])
                file_paths = [str(r.path) for r in resources if hasattr(r, "path")]
                entries.append(HistoryEntry(
                    description=description,
                    date=date,
                    files_affected=file_paths,
                ))
            return entries

        try:
            async with timed(_LOGGER, "rope.get_history"):
                return await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
        except Exception as exc:
            raise RopeError(f"rope get_history failed: {exc}") from exc

    # ── Change Stack ──

    async def begin_change_stack(self) -> str:
        """Start a new atomic change stack for chaining refactorings."""
        from rope.contrib.changestack import ChangeStack  # type: ignore[import-untyped]  # noqa: PLC0415

        project = self._require_project()
        self._change_stack = ChangeStack(project)
        self._change_stack.__enter__()  # pyright: ignore[reportAttributeAccessIssue]
        return "Change stack started"

    async def commit_change_stack(self) -> RefactorResult:
        """Commit and apply the current change stack."""
        if not hasattr(self, "_change_stack") or self._change_stack is None:
            raise RopeError("No active change stack to commit")
        self._change_stack.__exit__(None, None, None)  # pyright: ignore[reportAttributeAccessIssue]
        result = RefactorResult(
            edits=[], files_affected=[], description="Change stack committed", applied=True,
        )
        self._change_stack = None
        return result

    async def rollback_change_stack(self) -> str:
        """Discard the current change stack without applying."""
        if not hasattr(self, "_change_stack") or self._change_stack is None:
            raise RopeError("No active change stack to rollback")
        self._change_stack = None
        return "Change stack rolled back"

    # ── Multi-Project Refactoring ──

    async def multi_project_rename(
        self,
        additional_roots: list[str],
        file_path: str,
        line: int,
        character: int,
        new_name: str,
        apply: bool = False,
    ) -> RefactorResult:
        """Rename a symbol across multiple Rope projects simultaneously."""
        from rope.refactor.multiproject import MultiProjectRefactoring  # type: ignore[import-untyped]  # noqa: PLC0415

        project = self._require_project()

        def _work() -> RefactorResult:
            other_projects = [Project(root) for root in additional_roots]
            try:
                resource = self._resource_for_path(file_path)
                offset = self._position_to_offset(file_path, line, character)
                multi = MultiProjectRefactoring(Rename, [project, *other_projects])
                renamer = multi(project, resource, offset)
                project_changes = renamer.get_all_changes(new_name)
                all_edits: list[TextEdit] = []
                all_files: list[str] = []
                for proj, changes in project_changes:
                    for change in changes.changes:
                        if isinstance(change, ChangeContents):
                            file_path_str = str(Path(proj.root.real_path) / change.resource.path)
                            all_files.append(file_path_str)
                            all_edits.append(TextEdit(
                                file_path=file_path_str,
                                range=Range(
                                    start=Position(line=0, character=0),
                                    end=_end_position_for_content(change.resource.read()),
                                ),
                                new_text=change.new_contents,
                            ))
                if apply:
                    for proj, changes in project_changes:
                        proj.do(changes)
                return RefactorResult(
                    edits=all_edits,
                    files_affected=sorted(set(all_files)),
                    description=f"Multi-project rename to '{new_name}'",
                    applied=apply,
                )
            finally:
                for proj in other_projects:
                    proj.close()

        try:
            async with timed(_LOGGER, "rope.multi_project_rename"):
                return await asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout)
        except Exception as exc:
            raise RopeError(f"rope multi_project_rename failed: {exc}") from exc
