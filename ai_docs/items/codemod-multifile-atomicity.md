# codemod-multifile-atomicity — Multi-file codemod apply is not atomic

**row:** `codemod-multifile-atomicity` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tools/search/structural.py` (`structural_replace` per-file `apply_cst_transformer` loop)
- `src/python_refactor_mcp/tools/refactoring/security_autofix.py` (`security_autofix` — identical loop shape)
- `src/python_refactor_mcp/util/cst_apply.py` (`apply_cst_transformer` writes per call)

## Acceptance

- [ ] When `apply=True` spans multiple files and a later file fails (e.g. parse/transform error), earlier files are not left silently mutated with no result returned — either roll back the already-written files or return a structured partial-apply result naming what was written.
- [ ] Covers both `security_autofix` and `structural_replace` (shared helper preferred).
- [ ] Regression test: a 2-file batch where the 2nd file fails leaves file 1 unchanged OR the result reports the partial write.

## Evidence

- Surfaced by the cold implementation review of `structural_replace` (2026-06-19): with `apply=True` over multiple files, each file is written as the loop proceeds; a later failure raises `BackendError` with no `RefactorResult`, leaving earlier writes on disk. Pre-existing pattern copied from `security_autofix`, so it is a cross-tool gap, not a single-tool defect.

## Context

- Lower priority because the common path is single-file or preview-first; the change-stack primitives (`begin/commit/rollback_change_stack`) or a temp-write-then-rename batch could provide the atomicity.
