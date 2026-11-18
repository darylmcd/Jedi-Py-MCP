# server-startup-teardown-guard — Guard lifespan startup with teardown

**row:** `server-startup-teardown-guard` · **pri:** `Low` · **size:** `S` · **verified:** `de4d87d21cacd62dbbabf881188c339d330b98b7`

## Anchors

- `src/python_refactor_mcp/server.py:76-91`

## Acceptance

- [ ] `set_roots` and the eager `get_backends` run inside the `try/finally` that owns `shutdown_all`.
- [ ] Test: a failure in eager `get_backends` still calls `shutdown_all`.

## Evidence

- The lifespan runs `set_roots` and `get_backends` (server.py lines 81-83) before the `try` whose `finally` calls `shutdown_all`, so a startup failure skips teardown.
