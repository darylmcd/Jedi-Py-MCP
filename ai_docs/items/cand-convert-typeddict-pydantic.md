# cand-convert-typeddict-pydantic — Convert to TypedDict / Pydantic model

**row:** `cand-convert-typeddict-pydantic` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/util/cst_apply.py` (CST transform)
- `src/python_refactor_mcp/backends/pyright_lsp.py` (field-type inference)
- new tool module + registration (sibling to the dataclass slice)

## Acceptance

- [ ] TypedDict conversion for dict-shaped return values (keys → typed fields).
- [ ] Pydantic v2 model conversion for classes that already use type hints + validation logic.
- [ ] Preview-by-default; change-stack rollback; field types from Pyright inference.
- [ ] Unit tests cover a dict-shaped return → TypedDict and a typed class → Pydantic v2 model.

## Evidence

- The dataclass slice is already promoted (`cand-convert-to-dataclass`); the TypedDict and Pydantic variants are the remaining net-new modernization scope using the same CST machinery.

## Context

- Source brainstorm: BRAIN-003 (remaining brainstorm scope beyond the promoted dataclass slice). Do not duplicate `cand-convert-to-dataclass` — this row owns only the TypedDict + Pydantic variants.
