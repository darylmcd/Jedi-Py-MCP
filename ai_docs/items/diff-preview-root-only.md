# diff-preview-root-only — diff_preview must not resolve backends

**row:** `diff-preview-root-only` · **pri:** `High` · **size:** `M` · **verified:** `93cd1b324525daf60c5666c8f1107db9ce846b21`

## Anchors

- `src/python_refactor_mcp/tool_registry.py:1517-1526`
- `src/python_refactor_mcp/tool_runtime.py:216-232`
- `src/python_refactor_mcp/tool_runtime.py:358-375`
- `tests/unit/test_error_boundary.py:820-831`
- `tests/contract/test_mcp_protocol.py`

## Acceptance

- [ ] `ToolRecord` carries a `workspace` mode (`WorkspaceUse.BACKENDS` default, `WorkspaceUse.ROOT_ONLY`); `build_tools` passes it to `tool_error_boundary(func, *, workspace=...)`; the default keeps every existing caller and test unchanged.
- [ ] `ROOT_ONLY` resolves the workspace root from explicit paths only and never starts or touches backends: `_require_single_workspace`, then `registry.resolve_workspace_root(Path(first_path))`, then `_validate_params(kwargs, root)`; no `_current_backends.set`. No paths: root is None and only identifier validation runs (as the `backends is None` branch does today).
- [ ] `diff_preview`'s record uses `ROOT_ONLY`; its `_ = get_current_backends()` is deleted. `diff_preview(edits=[])` returns `[]`.
- [ ] `diff_preview` operates without resolving language backends. It succeeds with zero or multiple live backends when every edit is in an independently authorized path scope. Unscoped or escaping paths are rejected before disk access.
- [ ] Red-first real-registry tests (real `WorkspaceRegistry`; `_initialize_workspace` and backend classes patched to raise if reached; tmp_path layouts with `.git`), each seen failing on the old code: (1) empty registry, `edits=[]` returns `[]`; (2) in-scope edit with zero live backends succeeds, `registry._workspaces` stays empty, no backend constructor called; (3) in-scope edit while two unrelated workspaces are live succeeds and leaves both untouched (`last_accessed` unchanged).
- [ ] Existing escape/relative/mixed-workspace tests that assert the `get_backends` spy was awaited now assert it was NOT awaited; `_forbid_disk_diff` stays.
- [ ] Contract test: the `diff_preview` ToolRecord mode is `ROOT_ONLY`; `tool_error_boundary` default is `BACKENDS`.
- [ ] `changelog.d/fixed-diff-preview-no-backends.md` fragment.

## Evidence

- `tool_registry.py:1522`: `_ = get_current_backends()` is discarded; the boundary calls `registry.get_backends(edits[0].file_path)` (starts three backends) or, with `edits=[]`, falls to the path-less branch and raises `RuntimeError("No workspace backends available")` on an empty registry (probe at `f2d6074`, cold review 2026-09-28).
- Plan: `D:/Jedi-Py-MCP/.worktrees/bl-0056.report.md` (PR A of the bl-0056 split).

## Context

- Split out of `bl-0056` (PR A, merged before PR B). This row is being implemented now on branch `rem/bl-0056`; `bl-0056` (PR B) deps on it.
- Non-breaking and correct alone; removes the one tool that `bl-0056`'s strict path-less rule would otherwise wrongly reject (`diff_preview(edits=[])`).
- Follow-ups filed separately: `pure-file-tools-start-backends` (same mechanism, ~20 other tools), `real-registry-ctx-test-helper-spies`.
