"""Diff and file write utilities used by refactoring backends."""

from __future__ import annotations

import difflib
import os
import tempfile
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
		raise RopeError(
			f"Character out of range for line {position.line}: {position.character} > {max_character}"
		)

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


def write_atomic(file_path: str, content: str) -> None:
	"""Write file content atomically using a temp file and rename."""
	path = Path(file_path).resolve()
	path.parent.mkdir(parents=True, exist_ok=True)

	fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
	try:
		with os.fdopen(fd, "w", encoding="utf-8", newline="") as tmp_file:
			tmp_file.write(content)
		os.replace(tmp_name, str(path))
	except Exception as exc:
		with suppress(OSError):
			os.unlink(tmp_name)
		raise RopeError(f"Atomic write failed for {path}") from exc
