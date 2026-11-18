# pyright-publish-diagnostics-capability-stale — Client still declares the publishDiagnostics capability

**row:** `pyright-publish-diagnostics-capability-stale` · **pri:** `Low` · **size:** `S` · **verified:** `d390a382462fa0905eb6b9aae9c716a628ad6549`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py:371`

## Acceptance

- [ ] The declaration is removed and the integration suite still passes against real Pyright, or the reason to keep it is written beside it.

## Evidence

- Found by the PR #228 cold review and implementer: the handler and cache are gone, the capability declaration remains.
