# identifier-validators-unify — Unify remaining identifier validators

**row:** `identifier-validators-unify` · **pri:** `Low` · **size:** `M` · **verified:** `d15db23e2d9bb80d79c27643a4adeb33facef8a6`

## Anchors

- `src/python_refactor_mcp/util/shared.py`
- `src/python_refactor_mcp/backends/rope_backend.py`

## Acceptance

- [ ] No inline identifier regex or isidentifier check remains outside util.shared.
- [ ] Existing error-message tests updated, not weakened.

## Evidence

- Found by the PR #209 cold review (rope_backend.py ~735, class_extraction.py ~38).
