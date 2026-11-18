# non-nfkc-workspace-breaks-rope — One non-NFKC identifier makes every rope tool fail

**row:** `non-nfkc-workspace-breaks-rope` · **pri:** `Low` · **size:** `M` · **verified:** `56acf734d43c24c331918b47ac75a7fbe6956ad4`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py:427`
- `src/python_refactor_mcp/backends/rope_backend.py:1298`
- `src/python_refactor_mcp/backends/rope_backend.py:1320`

## Acceptance

- [ ] With one non-NFKC file in the workspace, a rope tool that does not touch that file succeeds, or fails with a typed error naming the file.
- [ ] Tests cover rename and one other rope tool beyond change_signature.

## Evidence

- Found in the PR #218 implementation sketches: only the change_signature path diagnoses it (_non_nfkc_identifier_error is called only at rope_backend.py:1299 and 1321), though rope fails while parsing modules for any tool.
