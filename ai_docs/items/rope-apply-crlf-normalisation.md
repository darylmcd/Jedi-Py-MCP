# rope-apply-crlf-normalisation — Rope apply rewrites CRLF to LF

**row:** `rope-apply-crlf-normalisation` · **pri:** `Low` · **size:** `S` · **verified:** `d15db23e2d9bb80d79c27643a4adeb33facef8a6`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py`

## Acceptance

- [ ] Applying a rope edit to a CRLF file keeps CRLF in unchanged lines.
- [ ] Test with a CRLF fixture asserting the applied bytes.

## Evidence

- Pre-existing: the rope-rename worker could not assert applied bytes for CRLF; only the preview text round-trips.
