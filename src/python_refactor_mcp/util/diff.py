"""Diff and file write utilities used by refactoring backends."""

from __future__ import annotations

import difflib
import os
import re
import tempfile
from collections import Counter
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from python_refactor_mcp.errors import RopeError
from python_refactor_mcp.models import Position, TextEdit

_TERMINATOR_SPLIT = re.compile(r"(\r\n|\r|\n)")
# Largest changed-middle size (old lines x new lines) diffed line by line; see the docstring.
_MAX_DIFF_CELLS = 160_000


def _normalize_newlines(text: str) -> str:
    """Translate ``\\r\\n`` and lone ``\\r`` to ``\\n`` (what ``Path.read_text`` yields)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def encode_with_line_endings(original: bytes, new_text: str) -> bytes:
    """Encode *new_text* (universal-newline text) as UTF-8 with *original*'s line endings.

    Edit planning reads files as universal-newline text, so planned text uses
    ``\\n``; this puts the file's own endings back at write time. ``\\r`` and
    ``\\r\\n`` inside *new_text* are normalised first, so *original* is the only
    authority on endings. Rules:

    * no terminator, or one terminator style throughout, in the original: every
      line ending becomes that style (no terminator at all means ``\\n``);
    * mixed original: a line equal to an original line (line diff) keeps that
      line's ending; a changed line takes the ending of the original line it
      replaces (paired by position inside the changed block); an inserted or
      unpaired line takes the dominant ending (most frequent; a tie goes to the
      ending seen first);
    * a ``\\r`` ending that would sit before an empty line ending in ``\\n`` is
      written as ``\\n`` (the two would read back as one ``\\r\\n``), so the line
      breaks of *new_text* always survive: the result, read with universal
      newlines, equals *new_text*;
    * whether the last line ends in a terminator follows *new_text*.

    A BOM is ordinary text here and round-trips. The mixed case trims the
    common leading and trailing lines (linear), then pairs the rest with
    ``difflib.SequenceMatcher`` only while ``len(old) * len(new)`` of the
    remaining lines is at most ``_MAX_DIFF_CELLS``; beyond that the changed
    lines are paired by position (inserts and deletes inside that middle shift
    the pairing). The cap bounds the real cost, which grows far faster than the
    pair count for duplicate-heavy input: measured on this host, blank-heavy
    500 x 500 lines 0.36 s, 1000 x 1000 3.0 s, 2000 x 2000 22.8 s, while
    identical lines are cheaper (2000 x 2000 0.36 s); at the cap the worst of
    all shapes tried (square and 20..8000-line skewed; blank-heavy, identical,
    distinct) was 0.18 s.
    """
    new = _normalize_newlines(new_text)
    old_parts = _TERMINATOR_SPLIT.split(original.decode("utf-8"))
    terminators = old_parts[1::2]
    if len(set(terminators)) <= 1:
        style = terminators[0] if terminators else "\n"
        return (new if style == "\n" else new.replace("\n", style)).encode("utf-8")

    old_bodies = old_parts[0::2]
    new_bodies = new.split("\n")
    counts = Counter(terminators)
    dominant = max(counts, key=lambda term: (counts[term], -terminators.index(term)))
    # For each new line, the index of the original line it corresponds to (or None).
    source: list[int | None] = [None] * len(new_bodies)
    head = 0
    limit = min(len(old_bodies), len(new_bodies))
    while head < limit and old_bodies[head] == new_bodies[head]:
        source[head] = head
        head += 1
    tail = 0
    while tail < limit - head and old_bodies[-1 - tail] == new_bodies[-1 - tail]:
        source[len(new_bodies) - 1 - tail] = len(old_bodies) - 1 - tail
        tail += 1
    old_mid = old_bodies[head : len(old_bodies) - tail]
    new_mid = new_bodies[head : len(new_bodies) - tail]
    if len(old_mid) * len(new_mid) <= _MAX_DIFF_CELLS:
        matcher = difflib.SequenceMatcher(None, old_mid, new_mid, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in ("equal", "replace"):
                for offset in range(min(i2 - i1, j2 - j1)):
                    source[head + j1 + offset] = head + i1 + offset
    else:
        # Too large to diff: pair the changed lines by position.
        for offset in range(min(len(old_mid), len(new_mid))):
            source[head + offset] = head + offset

    ends = [
        terminators[origin] if origin is not None and origin < len(terminators) else dominant for origin in source[:-1]
    ]
    # A "\r" ending before an empty line that ends in "\n" would read back as one "\r\n",
    # losing a line break. Right to left, so a change here is seen by the line before it.
    for index in range(len(ends) - 2, -1, -1):
        if ends[index] == "\r" and new_bodies[index + 1] == "" and ends[index + 1] == "\n":
            ends[index] = "\n"
    out: list[str] = []
    for index, body in enumerate(new_bodies):
        out.append(body)
        if index < len(ends):
            out.append(ends[index])
    return "".join(out).encode("utf-8")


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


def apply_text_edits_atomically(
    edits: list[TextEdit],
    *,
    expected_contents: dict[str, bytes] | None = None,
) -> list[str]:
    """Apply a multi-file edit set as one rollback-capable batch.

    Every source file is read and every updated payload is computed before the
    first write. If a later atomic write fails, already-written files are
    restored byte-for-byte. When *expected_contents* is supplied, every target
    must match the bytes used to generate its edits; stale input aborts before
    the first write. Returns the sorted affected paths.
    """
    edits_by_file: dict[str, list[TextEdit]] = {}
    for edit in edits:
        edits_by_file.setdefault(edit.file_path, []).append(edit)

    originals: dict[str, bytes] = {}
    updated: dict[str, bytes] = {}
    expected_by_path = (
        {str(Path(file_path).resolve()): content for file_path, content in expected_contents.items()}
        if expected_contents is not None
        else None
    )
    for file_path, file_edits in edits_by_file.items():
        path = Path(file_path).resolve()
        try:
            original_bytes = path.read_bytes()
            original_text = _normalize_newlines(original_bytes.decode("utf-8"))
        except (OSError, UnicodeError) as exc:
            raise RopeError(f"Cannot prepare atomic edit batch for {path}: {exc}") from exc
        resolved_path = str(path)
        if expected_by_path is not None:
            expected = expected_by_path.get(resolved_path)
            if expected is None:
                raise RopeError(f"Missing expected source for atomic edit target: {path}")
            if original_bytes != expected:
                raise RopeError(f"Stale edit source changed before atomic batch commit: {path}")
        originals[resolved_path] = original_bytes
        updated[resolved_path] = encode_with_line_endings(
            original_bytes,
            apply_text_edits(resolved_path, file_edits, content=original_text),
        )

    written: list[str] = []
    written_payloads: dict[str, bytes] = {}
    try:
        for file_path in sorted(updated):
            write_bytes_atomic_if_unchanged(file_path, updated[file_path], originals[file_path])
            written.append(file_path)
            written_payloads[file_path] = updated[file_path]
    except Exception as exc:
        rollback_failures: list[str] = []
        for file_path in reversed(written):
            try:
                write_bytes_atomic_if_unchanged(
                    file_path,
                    originals[file_path],
                    written_payloads[file_path],
                )
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


def _replace_atomic(
    file_path: str,
    writer: Callable[[int], None],
    error_message: str,
    expected_content: bytes | None = None,
) -> None:
    """Create a sibling temp file, populate it through *writer*, then replace."""
    path = Path(file_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        writer(fd)
        if expected_content is not None:
            try:
                current_content = path.read_bytes()
            except OSError as exc:
                raise RopeError(f"Cannot verify atomic-write source for {path}: {exc}") from exc
            if current_content != expected_content:
                raise RopeError(f"Stale edit source changed before atomic replace: {path}")
        os.replace(tmp_name, str(path))
    except RopeError:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise
    except Exception as exc:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise RopeError(f"{error_message} for {path}") from exc


def write_atomic(file_path: str, content: str) -> None:
    """Write universal-newline *content* atomically, keeping the target's line endings.

    The target's current bytes decide the endings (see :func:`encode_with_line_endings`);
    a new file is written with ``\\n``.
    """
    path = Path(file_path).resolve()
    try:
        current = path.read_bytes()
    except FileNotFoundError:
        current = b""
    except OSError as exc:
        raise RopeError(f"Cannot read atomic-write target {path}: {exc}") from exc
    write_bytes_atomic(file_path, encode_with_line_endings(current, content))


def write_atomic_if_unchanged(file_path: str, content: str, expected_content: bytes) -> None:
    """Atomically write universal-newline text only when the target still matches *expected_content*.

    Line endings follow *expected_content*, the bytes the edit was planned from.
    """
    write_bytes_atomic_if_unchanged(
        file_path,
        encode_with_line_endings(expected_content, content),
        expected_content,
    )


def write_bytes_atomic(file_path: str, content: bytes) -> None:
    """Write exact file bytes atomically without newline or encoding conversion."""

    def _write(fd: int) -> None:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(content)

    _replace_atomic(file_path, _write, "Atomic byte write failed")


def write_bytes_atomic_if_unchanged(
    file_path: str,
    content: bytes,
    expected_content: bytes,
) -> None:
    """Atomically write bytes only when the target still matches *expected_content*."""

    def _write(fd: int) -> None:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(content)

    _replace_atomic(
        file_path,
        _write,
        "Guarded atomic byte write failed",
        expected_content,
    )
