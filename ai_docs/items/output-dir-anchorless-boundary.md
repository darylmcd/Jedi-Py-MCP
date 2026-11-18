# output-dir-anchorless-boundary — Tie anchorless output_dir to its call's workspace

**row:** `output-dir-anchorless-boundary` · **pri:** `Low` · **size:** `M` · **verified:** `de4d87d21cacd62dbbabf881188c339d330b98b7`

## Anchors

- `src/python_refactor_mcp/tool_runtime.py:62`
- `src/python_refactor_mcp/tool_runtime.py:216-230`
- `src/python_refactor_mcp/tool_runtime.py:267-270`
- `src/python_refactor_mcp/util/shared.py:149-159`

## Acceptance

- [ ] Operator decision recorded: must an absolute `output_dir` lie inside the call's workspace?
- [ ] Per the decision, an anchorless call's `output_dir` is validated against the call's own workspace, not the most-recent one.
- [ ] Test: absolute `output_dir` outside the workspace is rejected when no path argument anchors the call.

## Evidence

- `DIR_PARAMS` values with no anchoring path argument resolve against the most-recent workspace (`registry.get_most_recent()`), not a workspace tied to the call.

## Context

Needs an operator decision first.
