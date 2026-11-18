# registry-resolve-root-mutates-unlocked — Make resolve_workspace_root pure

**row:** `registry-resolve-root-mutates-unlocked` · **pri:** `Low` · **size:** `M` · **verified:** `de4d87d21cacd62dbbabf881188c339d330b98b7`

## Anchors

- `src/python_refactor_mcp/workspace_registry.py:189-205`
- `src/python_refactor_mcp/tool_runtime.py:190-213`

## Acceptance

- [ ] `resolve_workspace_root` no longer mutates `_known_roots` / `_auto_roots`.
- [ ] Auto-discovered roots are registered on dispatch (in `get_backends`), under the registry lock.
- [ ] Test: a call rejected by `_require_single_workspace` or containment leaves `get_known_roots()` unchanged.
- [ ] Test: auto-root provenance still drives the explicit-vs-auto eviction preference.

## Evidence

- `resolve_workspace_root` appends to `_known_roots`/`_auto_roots` on a read, outside the lock, and now runs for every explicit path before `get_backends`, including calls later rejected.
