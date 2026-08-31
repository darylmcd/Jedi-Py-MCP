# cst-converter-format-drift — Normalize CST converter formatting

**row:** `cst-converter-format-drift` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tools/refactoring/dataclass_conversion.py`
- `src/python_refactor_mcp/tools/refactoring/typed_dict_conversion.py`
- `src/python_refactor_mcp/tools/refactoring/pydantic_conversion.py`
- `tests/unit/test_refactoring_tools.py`

## Acceptance

- [ ] Normalize these four files with the repository-pinned Ruff formatter and review the mechanical diff for semantic changes.
- [ ] Add a targeted formatter gate so drift in this converter surface is detected before merge.
- [ ] Run the focused converter tests plus `just ci`.

## Evidence

- `python -m ruff format --check` reported all four existing files would be reformatted; applying that broad mechanical rewrite inside the import-planning fix would obscure the behavioral review.
