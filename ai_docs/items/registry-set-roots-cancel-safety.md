# registry-set-roots-cancel-safety — Cancel-safe set_roots and _run_to_completion

**row:** `registry-set-roots-cancel-safety` · **pri:** `Low` · **size:** `S` · **verified:** `de4d87d21cacd62dbbabf881188c339d330b98b7`

## Anchors

- `src/python_refactor_mcp/workspace_registry.py:25-40`
- `src/python_refactor_mcp/workspace_registry.py:123-143`
- `src/python_refactor_mcp/workspace_registry.py:246-254`

## Acceptance

- [ ] `set_roots` does not replace `_known_roots`/`_auto_roots` until removed workspaces are shut down (or shuts them down cancel-safely), so a cancellation mid-loop leaves no removed root registered.
- [ ] `_run_to_completion` retrieves the shielded task's exception when the outer task is cancelled (non-Exception BaseException only), so none is left unretrieved.
- [ ] Tests cover cancellation mid-`set_roots` and a cleanup task that raises while the outer task is cancelled.

## Evidence

- `set_roots` replaces the root lists before its removal loop (same shape as `shutdown_all`); `_run_to_completion` leaves a shielded cleanup task's exception unretrieved.
