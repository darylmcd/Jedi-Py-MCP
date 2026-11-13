# rope-inline-default-sequence-validation — Validate inline defaults after preceding operations

**row:** `rope-inline-default-sequence-validation` · **pri:** `Medium` · **size:** `S` · **verified:** `7167e37ab6bce5e59dc547587724e3bda8eec6e9`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py:189-224`
- `tests/unit/test_rope_backend.py`

## Acceptance

- [ ] normalize then inline_default(index=1) on def f(a=1, b=2) returns a typed input error before emitting an invalid signature.

## Evidence

- After a prior normalize, the validator skips the earlier-default check even though normalize leaves the default list unchanged.
