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
