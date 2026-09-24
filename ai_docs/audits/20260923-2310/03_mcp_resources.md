# 03 — C2 Resource surface

| Check | Result | Evidence |
|---|---|---|
| `resources/list` (both profiles) | `resources: []` | `raw/inventory_*.json` → `"resources": {"resources": [], "resultType": "complete"}` |
| `resources/templates/list` (both profiles) | `resourceTemplates: []` | same |
| MIME / description / template substitution checks | N/A — nothing to read | — |
| Capability ↔ surface | `initialize.capabilities.resources = {subscribe:false, listChanged:false}` advertised with zero resources | `raw/inventory_*.json` `initialize.capabilities` |

## Findings

| ID | Sev | Finding | Row? |
|---|---|---|---|
| (info) resources-capability-without-resources | info | The `resources` capability is advertised although none are registered. This is the `mcp` SDK `MCPServer` default (not configured anywhere in `src/`), is spec-legal, and costs clients one empty list call. | No row — SDK default. |

## Candidate (not a finding)

Read-only state that agents currently fetch through tool calls could be exposed as resources (e.g. `server_status`, `list_environments`, `get_refactoring_history`). Product decision; no row proposed.
