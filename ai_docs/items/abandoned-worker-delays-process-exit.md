# abandoned-worker-delays-process-exit — An abandoned worker thread can delay process exit

**row:** `abandoned-worker-delays-process-exit` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/backends/_threading.py:98`
- `src/python_refactor_mcp/__main__.py:89`

## Acceptance

- [ ] A test or probe shows server stop completes within a bound while a worker is stuck.
- [ ] The strategy is recorded in ADR 0013 or a successor.

## Evidence

- Raised by the PR #225 cold review: ADR 0013 scopes its claim to shutdown_all, process exit is unaddressed and pre-existing.
