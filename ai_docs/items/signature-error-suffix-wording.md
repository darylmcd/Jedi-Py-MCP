# signature-error-suffix-wording — Non-NFKC error ends with a misleading parameter suffix

**row:** `signature-error-suffix-wording` · **pri:** `Low` · **size:** `S` · **verified:** `56acf734d43c24c331918b47ac75a7fbe6956ad4`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py:449`
- `src/python_refactor_mcp/backends/rope_backend.py:452`

## Acceptance

- [ ] The message no longer claims a parameter and names the offending files and spelling fix.
- [ ] The existing non-NFKC test asserts the new wording.

## Evidence

- Found in the PR #218 review. Existing test: tests/unit/test_rope_backend.py:396 (matches the (parameter: line) suffix).
