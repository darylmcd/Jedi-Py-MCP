# cand-refactor-transaction — Atomic multi-tool refactor transaction composite

**row:** `cand-refactor-transaction` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tools/composite.py` (current `diff_preview` home — transaction wrapper lands here)
- `src/python_refactor_mcp/backends/rope_backend.py` (`begin_change_stack` / `commit_change_stack` / `rollback_change_stack`)
- `src/python_refactor_mcp/models.py` (structured transaction result model)

## Acceptance

- [ ] `refactor_transaction` accepts an ordered `(tool, args)` list, executes each in preview (`apply=False`), and applies all under one change-stack — commit on success, rollback on any failure.
- [ ] Overlap/conflict detection across staged `TextEdit` sets; conflict-on-overlap = abort-and-rollback.
- [ ] Structured result: per-step status, applied/rolled-back, diff summary.
- [ ] Unit tests cover a 2-tool transaction success path and a mid-sequence failure that rolls back cleanly.

## Evidence

- Change-stack primitives already exist and most refactoring tools support `apply=False` preview. The missing piece is composition: today a multi-tool refactor is N independent applies, so a mid-sequence failure leaves a half-applied tree.

## Context

- Source brainstorm: BRAIN-012. Open planning question: are staged previews computed against the original source or the running (partially-edited) source — re-preview after each step vs offset reconciliation.
