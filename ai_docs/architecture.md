# Architecture

Purpose: compact architecture reference for AI contributors.

## System Layout

- Entry point: `src/python_refactor_mcp/__main__.py`
- Server lifecycle and tool registration: `src/python_refactor_mcp/server.py`
- Runtime discovery: `src/python_refactor_mcp/config.py`
- Shared models: `src/python_refactor_mcp/models.py`
- Backends: `src/python_refactor_mcp/backends/`
- Tool orchestration: `src/python_refactor_mcp/tools/`
- LSP and utility helpers: `src/python_refactor_mcp/util/`

## Backend Roles

- Pyright: type-aware semantic analysis over LSP.
- Jedi: dynamic fallback analysis.
- rope: mutation-safe refactoring edits.

## Runtime Flow

1. Server resolves workspace config and environment.
2. Lifespan initializes backends.
3. MCP tools route requests through orchestration modules.
4. Refactoring tools return edits by default, optionally apply changes.
5. Validation and diagnostics flow through Pyright integration.
