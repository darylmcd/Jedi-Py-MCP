# pull-many-swallows-programming-errors — _pull_many records programming errors as scan failures

**row:** `pull-many-swallows-programming-errors` · **pri:** `Low` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py:806`

## Acceptance

- [ ] A stand-in raising TypeError in one slot propagates out of get_diagnostics_many (test), while PyrightError stays a per-file result.

## Evidence

- Remaining half of bl-0052's second box after PR #226 and #228 (CancelledError propagation is done).
