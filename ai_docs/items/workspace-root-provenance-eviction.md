# workspace-root-provenance-eviction — Preserve workspace root provenance during eviction

**row:** `workspace-root-provenance-eviction` · **pri:** `Low` · **size:** `S` · **verified:** `7167e37ab6bce5e59dc547587724e3bda8eec6e9`

## Anchors

- `src/python_refactor_mcp/workspace_registry.py:194-207`
- `tests/unit/test_workspace_registry.py`

## Acceptance

- [ ] At capacity, an older explicit workspace is retained ahead of a newer auto-discovered workspace. LRU breaks ties within each class.

## Evidence

- Eviction treats every known root as explicit. Marker discovery inserts auto-discovered roots into the same collection.
