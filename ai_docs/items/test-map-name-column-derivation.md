# test-map-name-column-derivation — test_map derives name columns by substring

**row:** `test-map-name-column-derivation` · **pri:** `Low` · **size:** `S` · **verified:** `d15db23e2d9bb80d79c27643a4adeb33facef8a6`

## Anchors

- `src/python_refactor_mcp/tools/metrics/test_map.py`

## Acceptance

- [ ] Column comes from the AST node; test with a decorator containing the function name.

## Evidence

- Found while shipping bl-0051; untested.
