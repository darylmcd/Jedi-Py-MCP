# cand-convert-pydantic-v2 — Convert typed classes to Pydantic v2 models

**row:** `cand-convert-pydantic-v2` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tools/refactoring/pydantic_conversion.py` (new bounded converter)
- `src/python_refactor_mcp/tools/refactoring/__init__.py` (export)
- `src/python_refactor_mcp/tool_registry.py` (delegate and registration)
- `tests/unit/test_refactoring_tools.py` (supported validation shape plus rejection)

## Acceptance

- [ ] Define the exact eligible class shape and semantics-preserving mapping from existing validation logic to Pydantic v2 APIs before implementation.
- [ ] Reject constructors, descriptors, inheritance, or validators outside that proven shape without writing.
- [ ] Register a preview-first `convert_to_pydantic` tool with atomic apply and post-apply diagnostics.
- [ ] Cover one supported validation shape plus semantic-risk rejection in unit tests.

## Evidence

- Weaker evidence — BRAIN-003 proposal split from the TypedDict slice. The former umbrella did not define how arbitrary validation logic maps to Pydantic v2, so implementation must begin with a bounded source contract.
