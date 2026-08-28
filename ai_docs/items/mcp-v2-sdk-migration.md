# mcp-v2-sdk-migration — migrate the server to MCP SDK 2.x

**row:** `mcp-v2-sdk-migration` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/server.py` (FastMCP and Context imports plus lifecycle/tool signatures)
- `src/python_refactor_mcp/tool_registry.py` (FastMCP registration and ToolAnnotations construction)
- `tests/contract/test_mcp_protocol.py` (registered schema and annotation contract)
- `tests/integration/conftest.py` (real stdio client lifecycle)

## Acceptance

- [ ] Replace MCP 1.x imports, generic context annotations, and camel-case ToolAnnotations arguments with the supported MCP 2.x API without compatibility shims.
- [ ] Remove the `mcp<2` upper bound only after a clean source install resolves MCP 2.x and the server initializes over stdio.
- [ ] `list_tools` returns the complete live tool surface and preserves read-only, destructive, idempotent, and open-world annotations.
- [ ] Pyright, mypy, unit/contract tests, and the full stdio integration suite pass in the locked environment.

## Evidence

- Hosted CI run 33200285778 resolved `mcp==2.1.1` from the prior open-ended `mcp>=1.27` requirement and failed Pyright with 117 errors. MCP 2.x no longer exports the expected `FastMCP`/`Context` symbols from the 1.x import location and changed `ToolAnnotations` construction.
