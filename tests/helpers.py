"""Shared test helper factories for unit tests."""

from __future__ import annotations

from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import Diagnostic, Location, Position, Range, TextEdit


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
