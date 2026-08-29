"""Diff and file write utilities used by refactoring backends."""

from __future__ import annotations

import difflib
import os
import tempfile
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from python_refactor_mcp.errors import RopeError
from python_refactor_mcp.models import Position, TextEdit


def _position_to_index(content: str, position: Position) -> int:
    """Convert a 0-based position to a character index in content."""
    if position.line < 0 or position.character < 0:
        raise RopeError("Position line and character must be non-negative.")

    lines = content.splitlines(keepends=True)
    if not lines:
        lines = [""]

    if position.line >= len(lines):
        if position.line == len(lines) and position.character == 0:
            return len(content)
        raise RopeError(f"Line out of range for edit application: {position.line}")

    line_text = lines[position.line]
    max_character = len(line_text.rstrip("\r\n"))
    if position.character > max_character:
        raise RopeError(f"Character out of range for line {position.line}: {position.character} > {max_character}")

    prefix = lines[: position.line]
    return sum(len(part) for part in prefix) + position.character


def apply_text_edits(file_path: str, edits: list[TextEdit], content: str | None = None) -> str:
    """Apply a list of text edits to a file's current content and return new content.

    When *content* is provided it is used directly, avoiding an extra disk read.
    """
    if content is None:
        path = Path(file_path).resolve()
        content = path.read_text(encoding="utf-8")
    if not edits:
        return content

    ordered = sorted(
        edits,
        key=lambda edit: (
            edit.range.start.line,
            edit.range.start.character,
            edit.range.end.line,
            edit.range.end.character,
        ),
        reverse=True,
    )

    previous_start: int | None = None
    for edit in ordered:
        start = _position_to_index(content, edit.range.start)
        end = _position_to_index(content, edit.range.end)
        if end < start:
            raise RopeError("Invalid edit range: end precedes start.")

        if previous_start is not None and end > previous_start:
            raise RopeError("Overlapping text edits are not supported.")

        content = content[:start] + edit.new_text + content[end:]
        previous_start = start

    return content


def apply_text_edits_atomically(edits: list[TextEdit]) -> list[str]:
    """Apply a multi-file edit set as one rollback-capable batch.

    Every source file is read and every updated payload is computed before the
    first write. If a later atomic write fails, already-written files are
    restored byte-for-byte. Returns the sorted affected paths.
    """
    edits_by_file: dict[str, list[TextEdit]] = {}
    for edit in edits:
        edits_by_file.setdefault(edit.file_path, []).append(edit)

    originals: dict[str, bytes] = {}
    updated: dict[str, str] = {}
    for file_path, file_edits in edits_by_file.items():
        path = Path(file_path).resolve()
        try:
            original_bytes = path.read_bytes()
            original_text = original_bytes.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise RopeError(f"Cannot prepare atomic edit batch for {path}: {exc}") from exc
        resolved_path = str(path)
        originals[resolved_path] = original_bytes
        updated[resolved_path] = apply_text_edits(resolved_path, file_edits, content=original_text)

    written: list[str] = []
    try:
        for file_path in sorted(updated):
            write_atomic(file_path, updated[file_path])
            written.append(file_path)
    except Exception as exc:
        rollback_failures: list[str] = []
        for file_path in reversed(written):
            try:
                write_bytes_atomic(file_path, originals[file_path])
            except Exception:
                rollback_failures.append(file_path)
        if rollback_failures:
            failed = ", ".join(sorted(rollback_failures))
            raise RopeError(f"Atomic edit batch failed and rollback failed for: {failed}") from exc
        raise RopeError("Atomic edit batch failed; all written files were restored") from exc

    return sorted(updated)


def build_unified_diff(file_path: str, edits: list[TextEdit]) -> str:
    """Build a unified diff preview for the provided edits against current disk content."""
    path = Path(file_path).resolve()
    original = path.read_text(encoding="utf-8")
    updated = apply_text_edits(str(path), edits, content=original)
    diff_lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=str(path),
        tofile=str(path),
    )
    return "".join(diff_lines)


def _replace_atomic(file_path: str, writer: Callable[[int], None], error_message: str) -> None:
    """Create a sibling temp file, populate it through *writer*, then replace."""
    path = Path(file_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        writer(fd)
        os.replace(tmp_name, str(path))
    except Exception as exc:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise RopeError(f"{error_message} for {path}") from exc


def write_atomic(file_path: str, content: str) -> None:
    """Write file content atomically using a temp file and rename."""

    def _write(fd: int) -> None:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as tmp_file:
            tmp_file.write(content)

    _replace_atomic(file_path, _write, "Atomic write failed")


def write_bytes_atomic(file_path: str, content: bytes) -> None:
    """Write exact file bytes atomically without newline or encoding conversion."""

    def _write(fd: int) -> None:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(content)

    _replace_atomic(file_path, _write, "Atomic byte write failed")
