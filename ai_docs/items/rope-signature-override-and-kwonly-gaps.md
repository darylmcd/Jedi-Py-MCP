# rope-signature-override-and-kwonly-gaps — Rope signature gaps: overrides and keyword-only

**row:** `rope-signature-override-and-kwonly-gaps` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py`

## Acceptance

- [ ] Overriding methods are detected and refused (or updated) for rename/add/remove/reorder.
- [ ] Keyword-only targets are refused for every operation with a typed error.
- [ ] Tests for both.

## Evidence

- Documented as limits in ADR 0004 (rename check); the other operations are unchanged.

## Notes

2026-11-18 remediate: PR A (#216..#222 series) shipped same-name defs, *args refusal, typed errors. Planned B1 (cold-reviewed): refuse kw-only AND positional-only before DefinitionInfo.read; remove dead posonly branch of _positional_parameters and its test params (test_rope_backend.py ~449); update the ~1419 keyword-only test. Overrides: refusal is the correct fix but removes a capability, so operator sign-off is needed; recommendation: refuse base-side methods with overriders, keep derived-side (derived __init__ calling super().__init__ is changed correctly today). Known false negatives: override by assignment (m = lambda), type() dicts. Remainder row introduce-inline-parameter-kwonly must exist before B1 merges.
