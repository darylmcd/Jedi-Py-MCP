"""CLI entry point for python_refactor_mcp."""

from __future__ import annotations

import argparse
from pathlib import Path

from python_refactor_mcp import __version__
from python_refactor_mcp.server import run_server


def _build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for the MCP server entry point."""
    parser = argparse.ArgumentParser(
        prog="python -m python_refactor_mcp",
        description="Start the python-refactor-mcp stdio server. "
        "Workspace roots are discovered automatically from MCP clients or file paths.",
    )
    parser.add_argument(
        "workspace_root",
        nargs="?",
        help="Optional workspace root to pre-warm at startup. "
        "If omitted, workspaces are discovered dynamically.",
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

    run_server(workspace_root)


if __name__ == "__main__":
    main()
