# cand-change-signature-cst — Annotation-preserving change_signature via LibCST

**row:** `cand-change-signature-cst` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tools/refactoring/signature.py` (current `change_signature` orchestration)
- `src/python_refactor_mcp/backends/rope_backend.py` (`change_signature` + inline `ArgumentNormalizer` annotation-strip caveat)
- `src/python_refactor_mcp/util/cst_apply.py` (annotation-preserving edit emission)
- `src/python_refactor_mcp/tools/analysis/references.py` (`find_references` — call-site discovery)

## Acceptance

- [ ] A LibCST-backed path (`change_signature_cst`, or a CST post-pass on the rope path) does param rename + reorder WITHOUT stripping PEP 484/585 annotations or defaults, on the definition and call sites.
- [ ] Dry-run-first; change-stack rollback honored.
- [ ] Regression test: `change_signature` on an annotated function preserves all parameter annotations and defaults across def + call sites.

## Evidence

- `architecture.md` Known Gaps #1 and backlog row `known-rope-annotations` document a real, user-visible defect: `change_signature` silently drops type annotations. The LibCST foundation (#35) provides the workaround rope lacks.

## Context

- Source brainstorm: BRAIN-015. This is the **unblock path** for `known-rope-annotations` (Low) — coordinate, do not duplicate. The known-rope row stays as the documented rope limitation; this row implements the CST workaround.
- Open planning question: reimplement wholesale on LibCST, or keep rope for call-site discovery and add a thin CST post-pass that re-attaches dropped annotations.
