# ADR 0009 Register every tool through one record table

Date 2026-11-17

Status Accepted

## Context

Eleven tool delegates (`get_completions`, `get_inlay_hints`, `get_symbol_outline`, `argument_normalizer`, `argument_default_inliner`, `find_unused_imports`, `get_test_coverage_map`, `security_scan`, `security_autofix`, `structural_replace`, `server_status`) lived in `server.py` and were registered through a second table, `server.EXPLICIT_TOOL_RECORDS`, that every caller of `build_tools` / `tool_names_for_profile` had to pass as `extra_records`. Two registries described one tool boundary, and a change to a shared parameter (for example `root_path`) had to edit both files.

## Decision

- All delegates, their module constants and `_build_server_status` live in `tool_registry.py`; each tool is one `ToolRecord` in `TOOL_RECORDS`. The moved records are appended at the end of the table in their former order, so list order is unchanged.
- `EXPLICIT_TOOL_RECORDS` and the `extra_records` parameter of `build_tools` and `tool_names_for_profile` are removed. Both take `profile` only.
- `server.py` keeps the lifecycle (`build_server`, `workspace_lifespan`), instruction rendering and the entrypoint.
- The MCP tool surface is unchanged: for both profiles the serialized tool list (name, schema, annotations, meta, order) and the server instructions are byte-identical before and after.
- The moved delegates' debug logs now use the logger `python_refactor_mcp.tool_registry` (the name shared by every other delegate) instead of `python_refactor_mcp.server`. Error-boundary logs keep `python_refactor_mcp.server` (`tool_runtime`).

## Migration

This breaks Python importers of internal modules only; the console script, `python -m python_refactor_mcp` and every tool are unchanged.

| Before | After |
|---|---|
| `server.EXPLICIT_TOOL_RECORDS` | removed; the records are in `tool_registry.TOOL_RECORDS` |
| `build_tools(profile, extra_records=...)` | `build_tools(profile)` |
| `tool_names_for_profile(profile, extra_records=...)` | `tool_names_for_profile(profile)` |
| `(*TOOL_RECORDS, *server.EXPLICIT_TOOL_RECORDS)` | `TOOL_RECORDS` |
| `server.get_completions`, `get_inlay_hints`, `get_symbol_outline`, `argument_normalizer`, `argument_default_inliner`, `find_unused_imports`, `get_test_coverage_map`, `security_scan`, `security_autofix`, `structural_replace`, `server_status`, `_build_server_status` | same names in `tool_registry` |
| `server.READ_ONLY_ANNOTATIONS`, `server.DESTRUCTIVE_ANNOTATIONS`, `server.MultiWorkspaceContext` (re-exports) | import from `tool_registry` / `tool_runtime` |
| log filter on logger `python_refactor_mcp.server` for these eleven tools' debug lines | filter `python_refactor_mcp.tool_registry` |
