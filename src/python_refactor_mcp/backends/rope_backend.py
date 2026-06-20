"""rope backend implementation for mutation-oriented refactoring operations."""

from __future__ import annotations

import ast
import logging
import os
import re
from collections.abc import Callable
from difflib import SequenceMatcher
from itertools import zip_longest
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

from python_refactor_mcp.backends._threading import run_in_thread
from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import RopeError
from python_refactor_mcp.models import HistoryEntry, Position, Range, RefactorResult, SignatureOperation, TextEdit
from python_refactor_mcp.util.diff import apply_text_edits, write_atomic
from python_refactor_mcp.util.shared import end_position_for_content as _end_position_for_content

_LOGGER = logging.getLogger(__name__)
_DEFAULT_ROPE_TIMEOUT = 30.0

# Bounded set of position-based refactorings that may participate in a
# ``refactor_transaction``. Each maps to a rope primitive that yields a
# ``ChangeSet`` (see ``RopeBackend._build_step_changes``). Kept explicit so an
# unknown tool name fails with a structured error instead of a generic dispatch.
TRANSACTION_TOOLS: tuple[str, ...] = (
    "rename_symbol",
    "extract_method",
    "extract_variable",
    "inline_variable",
    "inline_method",
)


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

    @property
    def is_ready(self) -> bool:
        """Whether the rope project is open. Cheap, non-blocking."""
        return self._project is not None

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

    def apply_edits(self, edits: list[TextEdit]) -> list[str]:
        """Apply pre-computed text edits to disk with rollback on failure.

        Public entry so tools that post-process rope's preview edits (e.g.
        annotation-preserving ``change_signature``) can write the corrected
        edits through the same rollback-capable path rope uses internally.
        """
        return self._apply_edits(edits)

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

        result = await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.rename", logger=_LOGGER,
        )
        _LOGGER.debug("rope rename produced %d edits", len(result.edits))
        return result

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.extract_method", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.extract_variable", logger=_LOGGER,
        )

    async def inline(self, file_path: str, line: int, character: int, apply: bool) -> RefactorResult:
        """Inline a symbol and optionally apply edits."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)
            changes = create_inline(project, resource, offset).get_changes()
            return self._build_result(changes, "Inlined symbol", apply)

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.inline", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.move", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.introduce_parameter", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.encapsulate_field", logger=_LOGGER,
        )

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

            Rope's ``ArgumentNormalizer`` / ``ArgumentAdder`` re-emit the
            parameter list without Python 3 type annotations *or default
            values* (affects ``normalize`` / ``rename`` / ``reorder`` /
            ``add`` / ``remove``). The tool layer
            (``tools/refactoring/signature.py``) runs a LibCST post-pass that
            restores the **annotations**; default-value loss is still a known
            residual (backlog ``cand-change-signature-cst``).
        """

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            offset = self._position_to_offset(file_path, line, character)

            changers = _build_signature_changers(operations)
            changes = ChangeSignature(project, resource, offset).get_changes(changers)
            return self._build_result(changes, "Changed function signature", apply)

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.change_signature", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.restructure", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.use_function", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.introduce_factory", logger=_LOGGER,
        )

    async def module_to_package(self, file_path: str, apply: bool) -> RefactorResult:
        """Convert a module into a package preserving public imports."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            changes = ModuleToPackage(project, resource).get_changes()
            return self._build_result(changes, "Converted module to package", apply)

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.module_to_package", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.local_to_field", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.method_object", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.inline_method", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.inline_parameter", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.move_method", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.move_module", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.generate_code", logger=_LOGGER,
        )

    async def fix_module_names(self, apply: bool) -> RefactorResult:
        """Batch-rename modules to conform to PEP 8 lowercase naming."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            fixer = FixModuleNames(project)
            changes = fixer.get_changes()
            return self._build_result(changes, "Fixed module names to PEP 8 convention", apply)

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.fix_module_names", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.expand_star_imports", logger=_LOGGER,
        )

    async def relatives_to_absolutes(self, file_path: str, apply: bool) -> RefactorResult:
        """Convert all relative imports to absolute imports."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            organizer = ImportOrganizer(project)
            changes = organizer.relatives_to_absolutes(resource)
            return self._build_result(changes, "Converted relative imports to absolute", apply)

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.relatives_to_absolutes", logger=_LOGGER,
        )

    async def froms_to_imports(self, file_path: str, apply: bool) -> RefactorResult:
        """Convert ``from module import name`` to ``import module`` style."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            organizer = ImportOrganizer(project)
            changes = organizer.froms_to_imports(resource)
            return self._build_result(changes, "Converted from-imports to import statements", apply)

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.froms_to_imports", logger=_LOGGER,
        )

    async def handle_long_imports(self, file_path: str, apply: bool) -> RefactorResult:
        """Break long import lines per project preferences."""

        def _work() -> RefactorResult:
            project = self._require_project()
            project.validate(project.root)
            resource = self._resource_for_path(file_path)
            organizer = ImportOrganizer(project)
            changes = organizer.handle_long_imports(resource)
            return self._build_result(changes, "Handled long imports", apply)

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.handle_long_imports", logger=_LOGGER,
        )

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
            return await run_in_thread(
                _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.autoimport_search", logger=_LOGGER,
            )
        except RopeError as exc:
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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.find_errors", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.undo", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.redo", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.get_history", logger=_LOGGER,
        )

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

    # ── Atomic multi-step transaction ──

    @staticmethod
    def validate_transaction_steps(steps: list[tuple[str, dict[str, Any]]]) -> None:
        """Pre-flight validation for a transaction's whole step list.

        Pure (no project I/O): rejects an empty list, any step naming a tool
        outside :data:`TRANSACTION_TOOLS`, and any step missing a string
        ``file_path``. ALL steps are checked up front so an unknown tool in a
        later step is caught before the first step is pushed. Raises
        :class:`RopeError` — these are caller-correctable *input* errors, not
        execution failures, so they must surface as a raised tool error with
        nothing applied.
        """
        if not steps:
            raise RopeError("refactor_transaction requires at least one step")
        for index, (tool, args) in enumerate(steps):
            if tool not in TRANSACTION_TOOLS:
                raise RopeError(
                    f"transaction step {index} tool '{tool}' is not supported. "
                    f"Supported tools: {', '.join(TRANSACTION_TOOLS)}"
                )
            if not isinstance(args.get("file_path"), str):
                raise RopeError(
                    f"transaction step {index} ('{tool}') requires a string 'file_path' argument"
                )

    def _build_step_changes(self, tool: str, args: dict[str, Any]) -> ChangeSet:
        """Build the rope ``ChangeSet`` for one transaction step against running source.

        Re-reads the rope project for every call so each step previews against
        the *current* (partially-edited) tree — the resolved running-source
        model. Raises :class:`RopeError` for an unsupported tool or bad args.
        """
        project = self._require_project()
        project.validate(project.root)

        file_path = args.get("file_path")
        if not isinstance(file_path, str):
            raise RopeError(f"transaction step '{tool}' requires a string 'file_path' argument")
        resource = self._resource_for_path(file_path)

        if tool == "rename_symbol":
            offset = self._position_to_offset(file_path, int(args["line"]), int(args["character"]))
            return Rename(project, resource, offset).get_changes(str(args["new_name"]))
        if tool == "extract_method":
            start = self._position_to_offset(file_path, int(args["start_line"]), int(args["start_character"]))
            end = self._position_to_offset(file_path, int(args["end_line"]), int(args["end_character"]))
            return ExtractMethod(project, resource, start, end).get_changes(
                str(args["method_name"]), similar=bool(args.get("similar", False)),
            )
        if tool == "extract_variable":
            start = self._position_to_offset(file_path, int(args["start_line"]), int(args["start_character"]))
            end = self._position_to_offset(file_path, int(args["end_line"]), int(args["end_character"]))
            extractor = ExtractVariable(project, resource, start, end)
            return extractor.get_changes(str(args["variable_name"]))
        if tool in ("inline_variable", "inline_method"):
            offset = self._position_to_offset(file_path, int(args["line"]), int(args["character"]))
            return create_inline(project, resource, offset).get_changes()

        raise RopeError(
            f"transaction tool '{tool}' is not supported. Supported tools: {', '.join(TRANSACTION_TOOLS)}"
        )

    def _changed_char_spans(self, changes: ChangeSet) -> dict[str, set[tuple[int, int]]]:
        """Return, per absolute file path, the set of ``(line, col)`` cells a step changes.

        Computed by diffing each ``ChangeContents`` against current disk content
        (running-source coordinate space) at *character* granularity, so two
        independent edits on the same physical line do not falsely collide —
        only edits that touch the same span do. Lines whose length changes are
        marked from the first differing column to end-of-line on both sides.
        """
        spans: dict[str, set[tuple[int, int]]] = {}
        for change in changes.changes:
            if not isinstance(change, ChangeContents):
                continue
            absolute_file = _absolute_path(str(self._config.workspace_root / change.resource.path))
            old_lines = Path(absolute_file).read_text(encoding="utf-8").splitlines()
            new_lines = str(change.new_contents).splitlines()
            cells: set[tuple[int, int]] = set()
            for line_no, (old, new) in enumerate(zip_longest(old_lines, new_lines, fillvalue="")):
                if old == new:
                    continue
                matcher = SequenceMatcher(None, old, new)
                for op, i1, i2, _j1, _j2 in matcher.get_opcodes():
                    if op == "equal":
                        continue
                    # Mark touched columns on the OLD-side span (delete/replace)
                    # plus the OLD anchor column of inserts, so same-position
                    # rewrites in different steps collide.
                    for col in range(i1, max(i2, i1 + 1)):
                        cells.add((line_no, col))
            if cells:
                spans[absolute_file] = cells
        return spans

    async def apply_transaction(self, steps: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
        """Execute an ordered ``(tool, args)`` sequence atomically under one change stack.

        Pre-flight validation (empty list / unknown tool / missing ``file_path``)
        is the caller's responsibility via :meth:`validate_transaction_steps` and
        is NOT repeated here — by the time execution begins the step list is
        assumed well-formed. Each step previews against the running
        (partially-edited) source, is checked for overlap against character spans
        already touched in this transaction, then pushed onto a rope
        ``ChangeStack`` (which applies it to disk so the next step sees the
        mutation).

        On an *execution* failure — a step's refactoring raises mid-sequence, or
        an overlap is detected — the whole stack is rolled back via ``pop_all()``
        and a structured failure outcome is RETURNED (not raised), so the caller
        can report per-step status. Disk is left byte-identical to the
        pre-transaction state on abort.

        Returns a dict with keys:
        ``committed`` (bool), ``step_meta`` (list of per-applied-step dicts with
        ``tool``/``files_affected``/``edit_count``), ``failed_index`` (int index
        of the aborting step, or ``None`` on success) and ``error`` (the failure
        cause string, or ``None`` on success).
        """
        from rope.contrib.changestack import ChangeStack  # noqa: PLC0415

        def _work() -> dict[str, Any]:
            project = self._require_project()
            stack = ChangeStack(project, "refactor_transaction")
            touched: dict[str, set[tuple[int, int]]] = {}
            step_meta: list[dict[str, Any]] = []
            for index, (tool, args) in enumerate(steps):
                try:
                    changes = self._build_step_changes(tool, args)
                    step_spans = self._changed_char_spans(changes)

                    # Overlap guard: a step may not touch a character span already
                    # modified by an earlier step in this transaction.
                    for file_path, cells in step_spans.items():
                        prior = touched.get(file_path)
                        if prior is not None and prior & cells:
                            raise RopeError(
                                f"transaction step '{tool}' overlaps a prior step's edits in {file_path}; "
                                "aborting and rolling back."
                            )

                    stack.push(changes)
                except Exception as exc:
                    # Execution failure: revert every change already pushed in
                    # this transaction and report which step aborted and why.
                    stack.pop_all()
                    return {
                        "committed": False,
                        "step_meta": step_meta,
                        "failed_index": index,
                        "error": str(exc) or exc.__class__.__name__,
                    }

                files_affected = sorted(step_spans)
                for file_path, cells in step_spans.items():
                    touched.setdefault(file_path, set()).update(cells)
                step_meta.append({
                    "tool": tool,
                    "files_affected": files_affected,
                    "edit_count": len([c for c in changes.changes if isinstance(c, ChangeContents)]),
                })
            return {"committed": True, "step_meta": step_meta, "failed_index": None, "error": None}

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.apply_transaction", logger=_LOGGER,
        )

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

        return await run_in_thread(
            _work, timeout=self._timeout, error_cls=RopeError, op_name="rope.multi_project_rename", logger=_LOGGER,
        )
