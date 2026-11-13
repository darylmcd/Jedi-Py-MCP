# nested-workspace-multi-path-boundary — Validate every explicit workspace path

**row:** `nested-workspace-multi-path-boundary` · **pri:** `High` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tool_runtime.py:141-168`
- `src/python_refactor_mcp/tool_runtime.py:206-226`
- `src/python_refactor_mcp/util/shared.py:128-145`
- `tests/unit/test_error_boundary.py`

## Acceptance

- [ ] A mixed-root request fails before tool execution in either order. Same-root file lists, moves, and transactions still dispatch.

## Evidence

- The first path selects the backend. Remaining paths only need to be contained by that root, so outer-first requests can send nested worktree paths to the outer backend.
