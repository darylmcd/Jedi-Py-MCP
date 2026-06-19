# cand-type-stub-freshness — Type-stub freshness audit (.pyi vs .py drift)

**row:** `cand-type-stub-freshness` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tools/analysis/type_stubs.py` (`create_type_stubs` — regeneration hook + signature extraction to reuse)
- signature-comparison logic shared with `apply_type_annotations`
- new tool registration; result model in `src/python_refactor_mcp/models.py`

## Acceptance

- [ ] For projects shipping `.pyi` stubs alongside `.py` sources (or vendored stubs), diff stub signatures vs implementation signatures and surface drift.
- [ ] `@overload` and `Protocol` stubs handled without false-positive churn.
- [ ] Optional hook into `create_type_stubs` to regenerate drifted stubs.
- [ ] Unit tests cover a drifted stub (param added in impl) and an `@overload` stub that must not false-positive.

## Evidence

- Adjacent to `apply_type_annotations` (#36); reuses signature-comparison logic. Stub drift is a silent correctness gap for stub-shipping projects.

## Context

- Source brainstorm: BRAIN-008. Risk: `@overload`/`Protocol` handling is the main false-positive source — scope the first slice to plain function/method signatures.
