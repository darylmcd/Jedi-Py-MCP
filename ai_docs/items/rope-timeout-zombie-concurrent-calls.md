# rope-timeout-zombie-concurrent-calls — A timed-out rope call keeps running beside the next call

**row:** `rope-timeout-zombie-concurrent-calls` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/backends/_threading.py:60`
- `src/python_refactor_mcp/backends/rope_backend.py:589`
- `src/python_refactor_mcp/backends/rope_backend.py:1095`

## Acceptance

- [ ] A test shows a second rope call waits for (or is refused while) an abandoned worker on the same project is still running.
- [ ] The chosen policy (wait, refuse with a typed error) is documented.

## Evidence

- Raised by the threading-lease plan (PR #225): rope projects are not thread-safe; the abandoned worker now outlives the request by design, so the overlap window is real.
