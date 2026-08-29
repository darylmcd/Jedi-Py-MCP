"""Rename-related refactoring tools."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

import libcst as cst
from libcst.metadata import CodeRange, MetadataWrapper, PositionProvider, ScopeProvider

from python_refactor_mcp.models import DiffPreview, PrepareRenameResult, RefactorResult, TextEdit
from python_refactor_mcp.util.cst_apply import parse_module
from python_refactor_mcp.util.diff import build_unified_diff

from .helpers import post_apply_diagnostics

if TYPE_CHECKING:
    from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient
    from python_refactor_mcp.backends.rope_backend import RopeBackend


class _ImportAliasCollisionVisitor(cst.CSTVisitor):
    """Find a same-scope binding collision for the selected import alias."""

    METADATA_DEPENDENCIES = (PositionProvider, ScopeProvider)

    def __init__(self, line: int, character: int, new_name: str) -> None:
        self._line = line + 1  # LibCST positions are 1-based.
        self._character = character
        self._new_name = new_name
        self.collision: tuple[str, str] | None = None

    def visit_ImportAlias(self, node: cst.ImportAlias) -> None:
        if self.collision is not None or node.asname is None:
            return

        alias_name = node.asname.name
        if not isinstance(alias_name, cst.Name):
            return
        code_range = self.get_metadata(PositionProvider, alias_name)
        if not isinstance(code_range, CodeRange):
            return
        if not (
            code_range.start.line == self._line
            and code_range.start.column <= self._character < code_range.end.column
        ):
            return

        old_name = alias_name.value
        if old_name == self._new_name:
            return

        scope = self.get_metadata(ScopeProvider, node, None)
        if scope is None:
            return
        if any(assignment.name == self._new_name for assignment in scope.assignments):
            self.collision = (old_name, self._new_name)


def _ensure_import_alias_collision_free(
    file_path: str,
    line: int,
    character: int,
    new_name: str,
) -> None:
    """Reject an import-alias rename that would shadow an existing binding."""
    try:
        source = Path(file_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise ValueError(f"Rename collision preflight could not read the source file: {exc}") from exc

    module = parse_module(source, file_path)
    visitor = _ImportAliasCollisionVisitor(line, character, new_name)
    MetadataWrapper(module).visit(visitor)
    if visitor.collision is None:
        return

    old_name, conflicting_name = visitor.collision
    raise ValueError(
        f"Cannot rename import alias {old_name!r} to {conflicting_name!r}: "
        "the target name is already bound in the same scope."
    )


async def ensure_renameable(
    pyright: PyrightLSPClient,
    file_path: str,
    line: int,
    character: int,
) -> None:
    """Validate renameability before invoking rope operations."""
    preflight = await pyright.prepare_rename(file_path, line, character)
    if preflight is not None:
        return

    # Pyright can return null for valid positions in some dynamic contexts.
    # Keep a lightweight local guard for obvious invalid targets.
    lines = Path(file_path).read_text(encoding="utf-8").splitlines()
    if line < 0 or line >= len(lines):
        raise ValueError("Rename preflight failed: line is outside file bounds.")
    line_text = lines[line]
    if character < 0 or character >= len(line_text):
        raise ValueError("Rename preflight failed: character is outside line bounds.")
    target = line_text[character]
    if not (target.isalnum() or target == "_"):
        raise ValueError(
            "Rename preflight failed for the selected position. "
            "Choose an identifier location and retry."
        )


async def rename_symbol(
    pyright: PyrightLSPClient,
    rope: RopeBackend,
    file_path: str,
    line: int,
    character: int,
    new_name: str,
    apply: bool = False,
    include_diff: bool = False,
) -> RefactorResult:
    """Rename a symbol at the provided position."""
    await ensure_renameable(pyright, file_path, line, character)
    _ensure_import_alias_collision_free(file_path, line, character, new_name)
    result = await rope.rename(file_path, line, character, new_name, apply)
    result = await post_apply_diagnostics(pyright, result)

    if include_diff and not result.applied and result.edits:
        # Group edits by file and build diffs.
        edits_by_file: dict[str, list[TextEdit]] = defaultdict(list)
        for edit in result.edits:
            edits_by_file[edit.file_path].append(edit)
        diffs: list[DiffPreview] = []
        for fp, file_edits in sorted(edits_by_file.items()):
            diff_text = build_unified_diff(fp, file_edits)
            if diff_text:
                diffs.append(DiffPreview(file_path=fp, unified_diff=diff_text))
        result.diffs = diffs

    return result


async def prepare_rename(
    pyright: PyrightLSPClient,
    file_path: str,
    line: int,
    character: int,
) -> PrepareRenameResult | None:
    """Run rename preflight checks for the requested source position."""
    return await pyright.prepare_rename(file_path, line, character)
