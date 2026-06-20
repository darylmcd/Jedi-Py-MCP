# rollback-change-stack-noop — `rollback_change_stack` does not revert pushed changes

**row:** `rollback-change-stack-noop` · **pri:** `Medium` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py:968-973` (`rollback_change_stack` — sets `self._change_stack = None` and returns; never calls `ChangeStack.pop_all()` / `project.history.undo`).
- `src/python_refactor_mcp/backends/rope_backend.py:957-966` (`commit_change_stack` — calls `ChangeStack.__exit__(None, None, None)`; verify this actually applies the merged change rather than rope's `__exit__`-time `pop_all()` semantics).

## Acceptance

- [ ] `rollback_change_stack` actually reverts every change the stack pushed (call `ChangeStack.pop_all()` or undo via `project.history`), leaving disk byte-identical to the pre-stack state.
- [ ] Regression test: `begin_change_stack` → push/apply ≥1 real change → `rollback_change_stack` → assert the file on disk is unchanged from the start.
- [ ] Same investigation confirms `commit_change_stack` applies the intended merged change (add a commit-path test if its `__exit__` semantics turn out wrong too).

## Evidence

- Verified 2026-06-20: `rollback_change_stack` only nulls the reference. rope's `ChangeStack.push` applies each change to disk via `project.do`, so a non-empty stack's edits stay applied after "rollback" — the tool's documented contract ("Discard the current change stack without applying") is violated for any stack that pushed ≥1 change. Surfaced during the `cand-refactor-transaction` (#70) code-quality review.

## Context

- The shipped `refactor_transaction` (#70) deliberately uses `ChangeStack.pop_all()` directly and does NOT route through these broken tool methods, so it is unaffected — this row tracks the standalone `begin/commit/rollback_change_stack` MCP tools.
