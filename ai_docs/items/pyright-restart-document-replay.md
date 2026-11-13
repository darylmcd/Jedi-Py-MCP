# pyright-restart-document-replay — Restore document state on remaining LSP retries

**row:** `pyright-restart-document-replay` · **pri:** `Medium` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py:226-275`
- `src/python_refactor_mcp/backends/pyright_lsp.py:709-729`
- `tests/unit/test_pyright_lsp.py`

## Acceptance

- [ ] A file-bound request that crashes reopens the document on the replacement before replay.

## Evidence

- Several non-positional requests open the document before calling the generic crash-retry helper. A replacement session loses those opens.
