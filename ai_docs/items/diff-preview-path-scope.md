# diff-preview-path-scope — Define the filesystem boundary for diff previews

**row:** `diff-preview-path-scope` · **pri:** `High` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tool_registry.py:1517-1524`
- `src/python_refactor_mcp/tools/composite.py:23-33`
- `src/python_refactor_mcp/util/diff.py:143-154`
- `src/python_refactor_mcp/tool_runtime.py:206-226`

## Acceptance

- [ ] With an established workspace scope, a preview validates every edit path before disk access. An in-scope preview succeeds. An outside path or symlink escape is rejected.

## Evidence

- TextEdit.file_path goes straight to the disk read in build_unified_diff. The error boundary validates scalar and list paths but ignores paths nested in edits. The unified diff can disclose original content.
