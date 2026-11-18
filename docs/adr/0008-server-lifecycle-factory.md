# ADR 0008 Build the server through a factory instead of module state

Date 2026-11-17

Status Accepted

## Context

`server.py` built the MCP server at import time (`server.mcp`) with a module-level lifespan (`app_lifespan`). The CLI workspace root could therefore reach the lifespan only through a module global that `run_server` assigned (`global _workspace_root`, with a lint suppression), and two servers in one process shared that root. The lifespan also ran `set_roots` and the startup pre-warm before the `try` whose `finally` shuts the registry down, so teardown did not cover every startup step (a failure or cancellation there skipped `shutdown_all`).

## Decision

- `server.build_server(workspace_root: Path | None = None) -> MCPServer` builds one server per call; `workspace_lifespan(workspace_root)` returns its lifespan, with the root in a closure. No module-level server or root remains.
- Every startup step (`set_roots`, `prewarm`, context creation) runs inside the `try` whose `finally` calls `shutdown_all`.
- `run_server` resolves the CLI root and runs `build_server(root)`.
- The MCP tool surface (names, schemas, annotations, profiles) is unchanged.

## Migration

This breaks Python importers of the internal module API only; the console script, `python -m python_refactor_mcp` and every tool are unchanged.

| Before | After |
|---|---|
| `server.mcp` | `server.build_server()` (cold) or `server.build_server(root)` |
| `server.app_lifespan` | `server.workspace_lifespan(root)` (returns the lifespan callable) |
| assigning `server._workspace_root` | pass the root to `build_server` / `workspace_lifespan` |
