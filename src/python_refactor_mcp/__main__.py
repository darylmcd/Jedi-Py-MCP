"""CLI entry point for python_refactor_mcp."""

from __future__ import annotations

import sys
from pathlib import Path

from python_refactor_mcp.server import run_server


def main() -> None:
    """Parse CLI arguments and start the MCP server."""
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m python_refactor_mcp <workspace_root>")

    workspace_root = Path(sys.argv[1]).resolve()
    if not workspace_root.exists() or not workspace_root.is_dir():
        raise SystemExit(f"Workspace root does not exist or is not a directory: {workspace_root}")

    run_server(str(workspace_root))


if __name__ == "__main__":
    main()
