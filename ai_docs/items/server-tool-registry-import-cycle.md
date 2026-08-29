# server-tool-registry-import-cycle — Break the server/tool-registry import cycle

**row:** `server-tool-registry-import-cycle` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/server.py` (delayed `tool_registry` import near MCP construction)
- `src/python_refactor_mcp/tool_registry.py::register_tools`
- `src/python_refactor_mcp/tool_registry.py` (bottom-of-file `_get_current_backends` import)
- `tests/unit/test_server.py`

## Acceptance

- [ ] Production modules form no dependency cycle between `server.py` and `tool_registry.py`.
- [ ] Tool delegates and registration do not import private runtime state from each other through delayed imports.
- [ ] Tool profiles, annotations, backend lookup, and `_tool_error_boundary` behavior remain unchanged.
- [ ] One regression builds the production dependency graph and proves this cyclic component is absent.

## Evidence

- The package-aware dependency graph reports one strongly connected component containing `server.py` and `tool_registry.py`. `server.py` imports registration records/constants, while `tool_registry.py` imports `_tool_error_boundary` lazily and `_get_current_backends` at module tail; comments explicitly document the cycle workaround.
