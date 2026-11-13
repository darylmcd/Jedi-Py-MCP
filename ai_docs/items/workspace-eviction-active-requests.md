# workspace-eviction-active-requests — Keep active workspace backends alive through dispatch

**row:** `workspace-eviction-active-requests` · **pri:** `Medium` · **size:** `M` · **verified:** `7167e37ab6bce5e59dc547587724e3bda8eec6e9`

## Anchors

- `src/python_refactor_mcp/workspace_registry.py:194-216`
- `src/python_refactor_mcp/backends/pyright_lsp.py:225-280`
- `tests/unit/test_workspace_registry.py`

## Acceptance

- [ ] An in-flight request pins the workspace or is canceled explicitly. Eviction leaves no orphan process.

## Evidence

- LRU can shut down a backend during an active request. The request can then restart its Pyright process after the registry discards it.
