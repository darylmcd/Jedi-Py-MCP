# pyright-position-out-of-range-guard — Validate out-of-range positions on the Pyright read path

**row:** `pyright-position-out-of-range-guard` · **pri:** `Medium` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py:520` (`_position_request` — no file-bounds check on line/char before the LSP round-trip; cf. `rope_backend.py:177-186` which validates and raises)

(Regression test in `tests/unit/test_pyright_lsp.py` — see Acceptance.)

## Acceptance

- [ ] `_position_request` (or its callers) validates line/char against file bounds and raises a structured "position out of range" error instead of returning result=None/empty.
- [ ] find_references / goto_definition / get_type_info family distinguish a genuine zero-result from an invalid coordinate.
- [ ] Regression test passes an out-of-range coordinate and asserts a clear error, not silent empty.

## Evidence

- ui-ux + work-search concur (2026-06-19 discovery-sweep): live probe `find_references(line=999999)` returned `total_count:0` with no error; `rope_backend.py:177-186` validates and raises, the Pyright path does not — verified at HEAD 62f7d39.

## Context

- Behavioural/observability gap: a bad coordinate is indistinguishable from a true zero-reference symbol. Distinct from `pyright-position-request-param-merge-guard` (which guards `extra_params` envelope-key clobbering — a different defect on the same `_position_request` anchor).
