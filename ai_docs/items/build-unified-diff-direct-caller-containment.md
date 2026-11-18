# build-unified-diff-direct-caller-containment — Containment at the diff library seam

**row:** `build-unified-diff-direct-caller-containment` · **pri:** `Low` · **size:** `M` · **verified:** `de4d87d21cacd62dbbabf881188c339d330b98b7`

## Anchors

- `src/python_refactor_mcp/util/diff.py:144-157`
- `src/python_refactor_mcp/tools/composite.py:23-35`

## Acceptance

- [ ] Decision recorded: library-level containment, or documented statement that the MCP boundary is the only guard.
- [ ] If containment: `build_unified_diff` / `diff_preview` reject a path outside the workspace root with a typed error; test with a direct call.
- [ ] If documented: docstrings of both functions state the boundary-only guarantee.

## Evidence

- Both functions read `Path(file_path).resolve()` with no containment; only the MCP boundary (PR #202) protects them, so a direct library caller can read outside a workspace.
