# pyright-document-request-open-peer-sync — Hover/references requests do not resync other open documents

**row:** `pyright-document-request-open-peer-sync` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py:865`
- `src/python_refactor_mcp/tools/search/_helpers.py:49`

## Acceptance

- [ ] A test shows hover/references see a dependency edited on disk after it was opened.
- [ ] The cost per request is bounded (stat-gated, measured).

## Evidence

- Plan risk R1 of the pyright-diagnostics lane: deliberately excluded from PR #226 to keep scans linear.
