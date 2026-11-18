# signature-add-reorder-default-order-validation — Validate parameter order for add/reorder

**row:** `signature-add-reorder-default-order-validation` · **pri:** `Medium` · **size:** `S` · **verified:** `de4d87d21cacd62dbbabf881188c339d330b98b7`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py:191-211`
- `docs/adr/0004-signature-operation-validation.md`

## Acceptance

- [ ] The simulated walk in `_validate_signature_operations` rejects any `add` or `reorder` that leaves a non-default parameter after a defaulted one (`def f(a=1, b)`), with a typed input error naming the operation.
- [ ] Tests: add of a required parameter after a defaulted one, and a reorder placing a required parameter after a defaulted one, both rejected before any edit.
- [ ] ADR 0004 updated if the contract changes; `changed-breaking-*` fragment if newly rejected input.

## Evidence

- PR #201 validates `inline_default` against the signature earlier operations leave, but `add` and `reorder` can still emit invalid parameter order.
