"""Lint auto-fix tool wrapping ``ruff check --fix-only`` via asyncio subprocess.

Safety: arguments are passed as a list to ``asyncio.create_subprocess_exec`` — no shell is
spawned, no interpolation occurs. File paths are validated upstream by the server-level path
guard. Mirrors the subprocess pattern used by ``format.py``.
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


async def _ruff_fix_stdin(file_path: str, content: str, unsafe_fixes: bool = False) -> str:
    """Pipe *content* through ``ruff check --fix-only`` and return the fixed source.

    Uses ``--exit-zero`` so remaining-diagnostic exits are not confused with parse failures;
    only true subprocess errors (non-zero with empty stdout) raise ``BackendError``.
    """
    ruff = shutil.which("ruff")
    if ruff is None:
        raise BackendError(
            "ruff executable not found on PATH. Install ruff (declared as a project dependency) "
            "to use apply_lint_fixes."
        )
    args = [
        ruff,
        "check",
        "--fix-only",
        "--exit-zero",
        "--stdin-filename",
        file_path,
    ]
    if unsafe_fixes:
        args.append("--unsafe-fixes")
    args.append("-")

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate(content.encode("utf-8"))
    if proc.returncode != 0 and not stdout_bytes:
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
        raise BackendError(f"ruff check --fix failed for {file_path}: {stderr or 'unknown error'}")
    return stdout_bytes.decode("utf-8")


def _whole_file_edit(file_path: str, original: str, fixed: str) -> TextEdit:
    return TextEdit(
        file_path=file_path,
        range=Range(start=Position(line=0, character=0), end=end_position_for_content(original)),
        new_text=fixed,
    )


async def apply_lint_fixes(
    pyright: PyrightRefactoringBackend,
    file_path: str,
    apply: bool = False,
    file_paths: list[str] | None = None,
    unsafe_fixes: bool = False,
) -> RefactorResult:
    """Run ``ruff check --fix`` on one or more files and return whole-file replace edits.

    Preview mode is the default. When ``apply`` is True, changed files are written atomically and
    Pyright is notified so post-apply diagnostics reflect the new content. Files with no fixable
    issues are omitted from edits and files_affected. Set ``unsafe_fixes=True`` to also apply
    ruff's unsafe auto-fixes (those that may change runtime behavior).
    """
    targets = file_paths if file_paths is not None else [file_path]

    edits: list[TextEdit] = []
    files_affected: list[str] = []

    for fp in targets:
        try:
            original = Path(fp).read_text(encoding="utf-8")
        except (FileNotFoundError, OSError) as exc:
            raise BackendError(f"Cannot read file for lint fixing: {exc}") from exc

        fixed = await _ruff_fix_stdin(fp, original, unsafe_fixes=unsafe_fixes)
        if fixed == original:
            continue

        edits.append(_whole_file_edit(fp, original, fixed))
        files_affected.append(fp)

        if apply:
            write_atomic(fp, fixed)

    if not edits:
        return RefactorResult(
            edits=[],
            files_affected=[],
            description="No fixable lint issues found",
            applied=False,
        )

    description = f"Applied ruff lint fixes to {len(files_affected)} file(s)"
    result = RefactorResult(
        edits=edits,
        files_affected=sorted(set(files_affected)),
        description=description,
        applied=apply,
    )
    return await post_apply_diagnostics(pyright, result)
