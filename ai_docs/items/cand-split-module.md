# cand-split-module — New tool: partition a module into N modules by symbol selection

**row:** `cand-split-module` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/util/cst_apply.py` (`apply_cst_transformer_batch` — multi-file emit)
- `src/python_refactor_mcp/backends/rope_backend.py` (rope `Move` may handle import rewrites for a v1)
- new tool module + registration

## Acceptance

- [ ] `split_module` tool registered; partitions a module into N target modules by symbol selection.
- [ ] Import rewrites handled (rope `Move` acceptable for v1); preview-by-default.
- [ ] Unit tests cover a 2-way split with cross-module references.

## Evidence

- Weaker evidence — proposed candidate.
