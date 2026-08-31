# cst-plan-source-coherence — Bind CST semantic plans to source snapshots

**row:** `cst-plan-source-coherence` · **pri:** `High` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/util/cst_apply.py`
- `src/python_refactor_mcp/tools/refactoring/dataclass_conversion.py`
- `src/python_refactor_mcp/tools/refactoring/typed_dict_conversion.py`
- `src/python_refactor_mcp/tools/refactoring/pydantic_conversion.py`
- `tests/unit/test_cst_apply.py`
- `tests/unit/test_refactoring_tools.py`

## Acceptance

- [ ] Derive each semantic conversion plan and transformed preview from one verified source snapshot.
- [ ] Reject source drift before preview emission or apply; never apply an older field/validation plan to newer source.
- [ ] Add a regression that mutates the source between planning and transformation and proves no stale edit or write is returned.

## Evidence

- Current converters read once to build a semantic plan, then `apply_cst_transformer` reads again and applies that older plan to the newer parse; its atomic guard only protects the second read.

## Context

Keep the shared optimistic-concurrency write guard. Extend the contract so semantic planning is snapshot-coherent for preview and apply paths.
