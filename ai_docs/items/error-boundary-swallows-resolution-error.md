# error-boundary-swallows-resolution-error — Stop swallowing resolution errors; derive PATH_PARAMS in contract test

**row:** `error-boundary-swallows-resolution-error` · **pri:** `Low` · **size:** `S` · **verified:** `de4d87d21cacd62dbbabf881188c339d330b98b7`

## Anchors

- `src/python_refactor_mcp/tool_runtime.py:190-213`
- `tests/contract/test_mcp_protocol.py:241-265`
- `tests/unit/test_error_boundary.py:1182-1238`

## Acceptance

- [ ] `_require_single_workspace` no longer swallows `WorkspaceResolutionError` for non-anchor paths (or the later `_validate_params` message is proven equivalent and the swallow documented by a test).
- [ ] `test_path_params_are_validated` derives its expected path-param set from the live tool schemas (drift guard in `tests/unit/test_error_boundary.py`) instead of a hand-copied set.
- [ ] A new path parameter needs no manual edit to the contract test.

## Evidence

- Non-anchor paths with no enclosing root fail later with a different message; the contract test hand-copies `PATH_PARAMS`, so every boundary change needs a manual edit.
