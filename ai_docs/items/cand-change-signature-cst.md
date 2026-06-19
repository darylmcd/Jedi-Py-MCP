# cand-change-signature-cst — change_signature: default-value preservation + combined-op edge

**row:** `cand-change-signature-cst` · **pri:** `Low` · **size:** `M`

## Status

Annotation preservation **shipped** — `tools/refactoring/signature.py::change_signature` now runs a LibCST post-pass (`tools/refactoring/signature_annotations.py`) that re-attaches the parameter annotations rope drops (by name, and by original position for all-`rename` op sets). This row tracks the remaining residual.

## Anchors

- `src/python_refactor_mcp/tools/refactoring/signature_annotations.py` (extend `restore_param_annotations` to also carry defaults)
- `src/python_refactor_mcp/tools/refactoring/signature.py`

## Acceptance

- [ ] Parameter **default values** rope drops on rename/normalize are restored (annotations already are).
- [ ] The renamed parameter's annotation is restored under **combined** reorder+rename (currently skipped to avoid attaching a wrong type — see `test_mixed_reorder_and_rename_skips_index_restore`).
- [ ] Regression tests for both.

## Evidence

- Cold review of the annotation post-pass (2026-06-19) empirically confirmed rope also strips defaults, and that index-based restore is unsafe under position-shuffling ops (so the renamed param is intentionally left unannotated there).

## Context

- Source brainstorm: BRAIN-015. Defaults are semantically load-bearing (an `add`/`inline_default` op may change them intentionally), so restoration must be careful — diff against the original only where no op targets that parameter's default.
