# tool-registry-stale-registration-docstring — module docstring describes a registration mechanism that no longer exists

**row:** `tool-registry-stale-registration-docstring` · **pri:** `Low` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/tool_registry.py` (module docstring, lines 24-26)

## Acceptance

- [ ] The module docstring describes the actual mechanism: the eleven non-delegating wrappers are `ToolRecord` entries in `server.py::EXPLICIT_TOOL_RECORDS`, passed to `register_tools(..., extra_records=...)`.
- [ ] No remaining claim that any tool is registered via an `@mcp.tool` decorator in `server.py` (there are zero such decorators).
- [ ] Docstring agrees with `register_tools`'s own docstring in the same file.

## Evidence

- doc-audit bad-code-surfacing 2026-08-30. The module docstring states the eleven non-trivial wrappers "remain explicit ``@mcp.tool`` functions in ``server.py``". `grep -c '@mcp.tool' src/python_refactor_mcp/server.py` returns 0; the wrappers are `ToolRecord(...)` entries in `EXPLICIT_TOOL_RECORDS` (server.py:344-356). `register_tools`'s docstring in the same file already describes the correct mechanism, so the file contradicts itself.

## Context

- Almost certainly drifted during PR #91 (`refactor(server): break tool registry import cycle`). The tool *count* (eleven) is still accurate; only the mechanism description is stale. Stale comment on the file that defines the entire tool surface — the first thing an agent reads when adding a tool.
