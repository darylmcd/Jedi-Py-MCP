"""Code formatting tool wrapping ``ruff format`` via asyncio subprocess.

Note: this module uses ``asyncio.create_subprocess_exec`` (not shell-mode exec).
All arguments are passed as a list — no shell interpolation, no injection risk.
File paths are validated upstream by the server-level path guard.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import Position, Range, RefactorResult, TextEdit
from python_refactor_mcp.util.diff import write_atomic
from python_refactor_mcp.util.shared import end_position_for_content

from .helpers import PyrightRefactoringBackend, post_apply_diagnostics


async def _ruff_format_stdin(file_path: str, content: str) -> str:
    """Pipe *content* through ``ruff format --stdin-filename=<path>`` and return the result."""
    ruff = shutil.which("ruff")
    if ruff is None:
        raise BackendError(
            "ruff executable not found on PATH. Install ruff (declared as a project dependency) "
            "to use format_code."
        )
    proc = await asyncio.create_subprocess_exec(
        ruff,
        "format",
        "--stdin-filename",
        file_path,
        "-",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate(content.encode("utf-8"))
    if proc.returncode != 0:
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        raise BackendError(f"ruff format failed for {file_path}: {stderr or 'unknown error'}")
    return stdout_bytes.decode("utf-8")


def _whole_file_edit(file_path: str, original: str, formatted: str) -> TextEdit:
    return TextEdit(
        file_path=file_path,
        range=Range(start=Position(line=0, character=0), end=end_position_for_content(original)),
        new_text=formatted,
    )


async def format_code(
    pyright: PyrightRefactoringBackend,
    file_path: str,
    apply: bool = False,
    file_paths: list[str] | None = None,
) -> RefactorResult:
    """Run ruff-format on one or more files and return whole-file replace edits.

    Preview mode is the default. When ``apply`` is True, changed files are written atomically and
    Pyright is notified so post-apply diagnostics reflect the new content. Already-formatted files
    are omitted from edits and files_affected.
    """
    targets = file_paths if file_paths is not None else [file_path]

    edits: list[TextEdit] = []
    files_affected: list[str] = []

    for fp in targets:
        try:
            original = Path(fp).read_text(encoding="utf-8")
        except (FileNotFoundError, OSError) as exc:
            raise BackendError(f"Cannot read file for formatting: {exc}") from exc

        formatted = await _ruff_format_stdin(fp, original)
        if formatted == original:
            continue

        edits.append(_whole_file_edit(fp, original, formatted))
        files_affected.append(fp)

        if apply:
            write_atomic(fp, formatted)

    if not edits:
        return RefactorResult(
            edits=[],
            files_affected=[],
            description="All files already formatted",
            applied=False,
        )

    description = f"Formatted {len(files_affected)} file(s) with ruff-format"
    result = RefactorResult(
        edits=edits,
        files_affected=sorted(set(files_affected)),
        description=description,
        applied=apply,
    )
    return await post_apply_diagnostics(pyright, result)
