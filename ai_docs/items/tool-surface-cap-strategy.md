# tool-surface-cap-strategy — Preserve tool-discovery reliability headroom

**row:** `tool-surface-cap-strategy` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/config.py`
- `src/python_refactor_mcp/tool_registry.py`
- `src/python_refactor_mcp/server.py`
- `tests/unit/test_server.py`
- `tests/contract/test_mcp_protocol.py`

## Acceptance

- [ ] Define explicit tool profiles or a discovery mechanism that keeps each advertised surface within a documented reliability budget.
- [ ] Preserve access to every existing tool without increasing the default advertised surface beyond 100.
- [ ] Replace the exhausted global hard-cap assertion with per-profile contract tests and a completeness test across profiles.
- [ ] Document selection/configuration in the canonical runtime and domain references.

## Evidence

- `convert_to_dataclass` raises the live surface from 99 to the contract cap of 100, leaving no headroom for the remaining ready tool candidates.
