# Python Refactor Domain Reference

Purpose: compact entry point for the Python refactor MCP domain.

## Core Files

- `src/python_refactor_mcp/server.py`
- `src/python_refactor_mcp/config.py`
- `src/python_refactor_mcp/models.py`
- `src/python_refactor_mcp/backends/pyright_lsp.py`
- `src/python_refactor_mcp/backends/jedi_backend.py`
- `src/python_refactor_mcp/backends/rope_backend.py`
- `src/python_refactor_mcp/tools/analysis.py`
- `src/python_refactor_mcp/tools/navigation.py`
- `src/python_refactor_mcp/tools/refactoring.py`
- `src/python_refactor_mcp/tools/search.py`
- `src/python_refactor_mcp/tools/composite.py`

## Tool Surface Summary

- Analysis: references, type info, diagnostics.
- Navigation: definitions and call hierarchy.
- Refactoring: rename, extract, inline, move.
- Search/composite: constructor search, structural search, dead-code detection, import suggestions, smart rename.

## Deep Historical Material

- `ai_docs/archive/python-refactor-mcp-prompt.md`
