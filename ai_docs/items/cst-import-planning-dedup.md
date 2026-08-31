# cst-import-planning-dedup — Centralize CST import planning

**row:** `cst-import-planning-dedup` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/util/cst_imports.py` (new shared helper)
- `src/python_refactor_mcp/tools/refactoring/dataclass_conversion.py`
- `src/python_refactor_mcp/tools/refactoring/typed_dict_conversion.py`
- `src/python_refactor_mcp/tools/refactoring/pydantic_conversion.py`
- `tests/unit/test_refactoring_tools.py`

## Acceptance

- [ ] Share top-level binding discovery, collision-safe alias selection, and docstring/future-aware import insertion across all three converters.
- [ ] Preserve each converter's supported import forms and fail-closed wildcard behavior.
- [ ] Add one table-driven regression for existing imports, alias collisions, and late rebindings.

## Evidence

- The three converter modules independently implement overlapping import binding and insertion algorithms, increasing drift risk at the generated-code boundary.

## Context

Keep converter-specific policy in each tool. Extract only syntax-level import planning and collision detection.
