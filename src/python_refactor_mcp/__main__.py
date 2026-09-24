"""CLI entry point for python_refactor_mcp."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import TextIO

from python_refactor_mcp import __version__
from python_refactor_mcp.server import run_server

_PACKAGE_LOGGER_NAME = "python_refactor_mcp"
_BACKEND_FAILURE_EVENT = "tool_backend_failure"
# Only these structured fields are rendered; they are path-free by construction
# (see tool_runtime._safe_failure_diagnostics). Never add args or payload fields.
_BACKEND_FAILURE_KEYS = ("failure_id", "exception_types", "traceback_locations")


class BackendFailureFormatter(logging.Formatter):
    """Render package log records, appending whitelisted backend-failure diagnostics."""

    def __init__(self) -> None:
        super().__init__("%(levelname)s %(name)s: %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        """Format *record*; ``tool_backend_failure`` records gain their redacted diagnostics."""
        rendered = super().format(record)
        if getattr(record, "event", None) != _BACKEND_FAILURE_EVENT:
            return rendered
        fields: list[str] = []
        for key in _BACKEND_FAILURE_KEYS:
            if not hasattr(record, key):
                continue
            value = getattr(record, key)
            if isinstance(value, tuple):
                value = list(value)
            fields.append(f"{key}={json.dumps(value)}")
        return f"{rendered} {' '.join(fields)}" if fields else rendered


class StderrDiagnosticsHandler(logging.StreamHandler[TextIO]):
    """Stderr handler for the package logger; stdout is reserved for the MCP stdio transport."""

    def __init__(self) -> None:
        super().__init__(sys.stderr)
        self.setFormatter(BackendFailureFormatter())


def _install_stderr_diagnostics() -> None:
    """Attach one stderr diagnostics handler to the package logger (idempotent).

    The MCP SDK's ``MCPServer`` constructor calls ``logging.basicConfig`` with a
    bare ``%(message)s`` root handler, so package records stop propagating once
    this handler owns them; otherwise every line would print twice. Level
    filtering still follows the root level the SDK configures.
    """
    logger = logging.getLogger(_PACKAGE_LOGGER_NAME)
    logger.propagate = False
    if any(isinstance(handler, StderrDiagnosticsHandler) for handler in logger.handlers):
        return
    logger.addHandler(StderrDiagnosticsHandler())


def _build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for the MCP server entry point."""
    parser = argparse.ArgumentParser(
        prog="python -m python_refactor_mcp",
        description="Start the python-refactor-mcp stdio server. "
        "Workspace roots are discovered automatically from tool request file paths.",
    )
    parser.add_argument(
        "workspace_root",
        nargs="?",
        help="Optional workspace root to pre-warm at startup. "
        "If omitted, workspaces are discovered from tool request file paths.",
    )
    parser.add_argument("--version", action="version", version=f"python-refactor-mcp {__version__}")
    return parser


def main() -> None:
    """Parse CLI arguments and start the MCP server."""
    parser = _build_parser()
    args = parser.parse_args()

    workspace_root: str | None = None
    if args.workspace_root is not None:
        resolved = Path(args.workspace_root).resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise SystemExit(f"Workspace root does not exist or is not a directory: {resolved}")
        workspace_root = str(resolved)

    _install_stderr_diagnostics()
    run_server(workspace_root)


if __name__ == "__main__":
    main()
