# output-dir-anchorless-boundary — Tie anchorless output_dir to its call's workspace

**row:** `output-dir-anchorless-boundary` · **pri:** `Low` · **size:** `M`

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

- Premise changed by PR #208: the most-recent / CLI-root fallback was deleted. An anchorless call's `output_dir` now resolves against the sole selected workspace (`registry.implicit_workspace()`), or the call fails with `AMBIGUOUS_WORKSPACE` when none or several are live. The remaining question is only the operator decision above: must an absolute `output_dir` lie inside that workspace?
- Re-derive the anchors against `tool_runtime.py` after #208 before implementing; `tool_runtime.py:216-230` and `:267-270` moved.

## Context

Needs an operator decision first.
