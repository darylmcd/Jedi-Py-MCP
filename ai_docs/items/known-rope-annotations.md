# known-rope-annotations — change_signature drops parameter default values

**row:** `known-rope-annotations` · **pri:** `Low` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py` (rope `ArgumentNormalizer`/`ArgumentAdder` re-emit params without annotations *or defaults*)
- `src/python_refactor_mcp/tools/refactoring/signature_annotations.py` (the shipped annotation-restore post-pass — extend here for defaults)

## Acceptance

- [ ] `change_signature` on a function with parameter defaults preserves those defaults on rename/normalize (defaults are currently dropped by rope and NOT yet restored).
- [ ] Regression test covering default-value preservation.

## Evidence

- Type annotations are now restored by the LibCST post-pass (shipped). Verified residual: rope's `rename` also strips the renamed parameter's default value (`def greet(name: str, count: int = 3)` → rename `count`→`n` loses the `= 3`). The post-pass restores annotations only (slice 1).

## Context

- The annotation strip — the original user-visible defect — is fixed. This row now tracks only the default-value residual; coordinate with `cand-change-signature-cst`.
