# cand-extract-class — New tool: extract cohesive fields/methods into a collaborator class

**row:** `cand-extract-class` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/util/cst_apply.py` (CST apply foundation)
- new tool module + registration

## Acceptance

- [ ] `extract_class` tool registered; moves a selected subset of fields/methods into a new collaborator class.
- [ ] Preview-by-default; unit tests cover field + method extraction and delegation wiring.

## Evidence

- Weaker evidence — proposed candidate. Verified: rope 1.14 ships no `ExtractClass`; implementation uses the in-repo CST foundation.
