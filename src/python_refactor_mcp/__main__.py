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
        description="Start the python-refactor-mcp stdio server for a workspace.",
    )
    parser.add_argument("workspace_root", nargs="?", help="Workspace root to analyze and refactor.")
    parser.add_argument("--version", action="version", version=f"python-refactor-mcp {__version__}")
    return parser


def main() -> None:
    """Parse CLI arguments and start the MCP server."""
    parser = _build_parser()
    args = parser.parse_args()
    if args.workspace_root is None:
        parser.error("the following arguments are required: workspace_root")

    workspace_root = Path(args.workspace_root).resolve()
    if not workspace_root.exists() or not workspace_root.is_dir():
        raise SystemExit(f"Workspace root does not exist or is not a directory: {workspace_root}")

    run_server(str(workspace_root))


if __name__ == "__main__":
    main()
