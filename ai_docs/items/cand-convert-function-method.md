# cand-convert-function-method — Symmetric tools: convert_function_to_method / convert_method_to_function

**row:** `cand-convert-function-method` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/util/cst_apply.py` (CST apply foundation)
- `src/python_refactor_mcp/tools/analysis/references.py` (caller rewrites via `find_references`)
- new tool module + registration

## Acceptance

- [ ] Both directions registered as tools; caller sites rewritten via `find_references`.
- [ ] Preview-by-default; unit tests cover each direction including caller rewrites.

## Evidence

- Weaker evidence — proposed candidate; CST foundation exists.
