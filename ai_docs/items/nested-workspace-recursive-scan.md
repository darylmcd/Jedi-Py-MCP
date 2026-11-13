# nested-workspace-recursive-scan — Keep recursive scans inside the selected workspace

**row:** `nested-workspace-recursive-scan` · **pri:** `Medium` · **size:** `M` · **verified:** `7167e37ab6bce5e59dc547587724e3bda8eec6e9`

## Anchors

- `src/python_refactor_mcp/util/file_filter.py:26-43`
- `src/python_refactor_mcp/tools/analysis/diagnostics.py:101-106`

## Acceptance

- [ ] A recursive scan of the enclosing workspace excludes a nested workspace. Explicitly selecting the nested workspace scans its files.

## Evidence

- The shared walker prunes fixed directory names. A scan from an enclosing root can analyze nested worktree files under the enclosing backend.
