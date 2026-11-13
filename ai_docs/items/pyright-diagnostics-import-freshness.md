# pyright-diagnostics-import-freshness — Refresh changed imports before diagnostic analysis

**row:** `pyright-diagnostics-import-freshness` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py:544-581`
- `src/python_refactor_mcp/tools/analysis/diagnostics.py:101-115`
- `tests/integration/test_end_to_end.py`

## Acceptance

- [ ] A changed open dependency is reflected immediately when reading diagnostics for its unchanged importer.

## Evidence

- Explicit diagnostics synchronize only the requested file. An opened dependency edited on disk can remain stale in the language server when its importer is analyzed.
