# cst-converter-preflight-dedup — Share CST converter preflights

**row:** `cst-converter-preflight-dedup` · **pri:** `Low` · **size:** `M` · **deps:** `split-semantic-converter-tests`

## Anchors

- `src/python_refactor_mcp/tools/refactoring/dataclass_conversion.py`
- `src/python_refactor_mcp/tools/refactoring/pydantic_conversion.py`
- new private converter-preflight helper
- `tests/unit/test_refactoring_tools.py`

## Acceptance

- [ ] Extract duplicated top-level class selection, comment detection, and mutable-default classification behind one private collaborator.
- [ ] Preserve converter-specific caller errors and fail-closed source-shape eligibility.
- [ ] Add focused shared-helper regressions and run `just ci`.

## Evidence

- The dataclass and Pydantic converters independently implement the same comment visitor, top-level class lookup, and mutable-default predicate.
Sequencing: complete `split-semantic-converter-tests` first; add shared-helper coverage to the resulting `tests/unit/test_semantic_converters.py` module.
