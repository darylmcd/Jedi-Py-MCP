# cand-structural-replace — New tool: structural find-and-replace codemod

**row:** `cand-structural-replace` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tools/search/structural.py` (`structural_search` — the AST-shaped *find* half to reuse; check whether its pattern syntax exposes capture/metavariables reusable in a replacement template)
- `src/python_refactor_mcp/util/cst_apply.py` (`apply_cst_transformer` — safe *mutation* half)
- new tool module + registration; `RefactorResult` in `src/python_refactor_mcp/models.py`

## Acceptance

- [ ] `structural_replace(pattern, replacement, file_paths, apply=False) -> RefactorResult` registered; preview-by-default.
- [ ] Slice 1: single-metavariable rewrite (e.g. `logger.warn($X)` → `logger.warning($X)`) via the existing structural matcher + LibCST emit.
- [ ] Overlapping-match contract defined (abort-on-conflict); dry-run-first + change-stack rollback honored.
- [ ] Unit tests cover a single-capture rewrite with comment/format preservation.

## Evidence

- `structural_search` already implements the find half; the LibCST apply scaffold (#35) implements safe mutation. The *replace* half is the single headline parity gap vs best-in-class structural-codemod tools.

## Context

- Distinct from `cand-security-autofix` (security-specific codemod) — this is the general structural engine that the security autofix could later dispatch through.
- Source brainstorm: BRAIN-014. Open planning question: pattern-syntax reuse vs a dedicated replace parser.
