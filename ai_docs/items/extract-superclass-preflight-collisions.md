# extract-superclass-preflight-collisions — Harden extract_superclass collision and scope preflights

**row:** `extract-superclass-preflight-collisions` · **pri:** `Medium` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/tools/refactoring/superclass.py`
- `tests/unit/test_refactoring_tools.py`

## Acceptance

- [ ] Reject a base class name equal to the source class or any existing top-level binding before emitting edits.
- [ ] Reject duplicate requested members and duplicate top-level source-class definitions instead of transforming multiple or reporting a misleading member count.
- [ ] Keep nested classes with the same name outside the selected top-level class unchanged.
- [ ] Unit tests cover each collision and scope boundary in preview mode and prove the source file remains unchanged.

## Evidence

- Adjacent review on 2026-08-30 found that `ExtractSuperclassTransformer.leave_ClassDef` matches by name at every nesting level, accepts duplicate member requests, and emits a new base without checking module bindings or self-inheritance.
