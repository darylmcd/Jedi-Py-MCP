# pyright-validate-position-redundant-read — reuse cached content in `_validate_position`

**row:** `pyright-validate-position-redundant-read` · **pri:** `Low` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py` (`_validate_position` — unconditional `Path(absolute_path).read_text()` per call) vs `ensure_file_open` (reads/caches the same file immediately before).

## Acceptance

- [ ] Position validation reuses the content already loaded by `ensure_file_open` (or the cached source) rather than issuing a second full-file `Path.read_text` on every position request.
- [ ] Warm-path position requests (file already in `_open_files`) perform at most one disk read for the request; regression test asserts no extra read on the warm path.

## Evidence

- `pyright-position-out-of-range-guard` (#71) code-quality review (2026-06-20): `_validate_position` backs ~12 `textDocument/*` position tools and does a redundant full-file read on the warm path (where `ensure_file_open` early-returns). Reviewer rated Medium (hot path + sync read in `async def`); real-world latency impact is small because each call is dominated by the LSP round-trip, hence **Low** priority — hygiene, not user-facing latency.

## Context

- May require `ensure_file_open` to retain the decoded text (it currently caches only a content hash); if so, the caching change is the bulk of this row.
