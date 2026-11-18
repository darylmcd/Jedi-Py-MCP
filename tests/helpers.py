"""Shared test helper factories for unit tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import Diagnostic, Location, Position, Range, TextEdit


def many_from(
    per_file: Callable[[str], Awaitable[list[Diagnostic]]],
) -> Callable[..., Awaitable[list[Any]]]:
    """Adapt a per-file coroutine to the backend's ``get_diagnostics_many`` result shape."""

    async def many(
        paths: list[str], *, concurrency: int = 1, stop_on_error: bool = False
    ) -> list[list[Diagnostic] | Exception]:
        results: list[list[Diagnostic] | Exception] = []
        for path in paths:
            try:
                results.append(await per_file(path))
            except Exception as exc:
                results.append(exc)
                if stop_on_error:
                    break
        return results

    return many


def many_returning(result: list[Diagnostic] | Exception) -> Callable[..., Awaitable[list[Any]]]:
    """A ``get_diagnostics_many`` stand-in giving every file the same diagnostics or failure."""

    async def per_file(_path: str) -> list[Diagnostic]:
        if isinstance(result, Exception):
            raise result
        return result

    return many_from(per_file)


def make_location(path: str, line: int, character: int) -> Location:
    return Location(
        file_path=path,
        range=Range(
            start=Position(line=line, character=character),
            end=Position(line=line, character=character + 1),
        ),
    )


def make_edit(path: str) -> TextEdit:
    return TextEdit(
        file_path=path,
        range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
        new_text="x",
    )


def make_diag(path: str, line: int) -> Diagnostic:
    return Diagnostic(
        file_path=path,
        range=Range(start=Position(line=line, character=0), end=Position(line=line, character=1)),
        severity="error",
        message=f"e{line}",
        code=None,
    )


def make_config(tmp_path: Path) -> ServerConfig:
    return ServerConfig(
        workspace_root=tmp_path,
        python_executable=tmp_path / ".venv" / "Scripts" / "python.exe",
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )
