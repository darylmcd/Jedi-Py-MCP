# pyright-workspace-diagnostic-snapshot — Analyze pathless diagnostics across the workspace

**row:** `pyright-workspace-diagnostic-snapshot` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py:544-581`
- `src/python_refactor_mcp/tool_registry.py:288-306`
- `tests/integration/test_end_to_end.py`

## Acceptance

- [ ] The first pathless call reports known diagnostics in the workspace and preserves the documented error semantics.

## Evidence

- Pathless diagnostics return only the push cache. In open-files-only mode a fresh session reports an empty result before any file is opened.
