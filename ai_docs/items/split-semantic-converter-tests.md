# split-semantic-converter-tests — Isolate semantic converter tests

**row:** `split-semantic-converter-tests` · **pri:** `Low` · **size:** `S`

## Anchors

- `tests/unit/test_refactoring_tools.py` (semantic converter sections)
- new `tests/unit/test_semantic_converters.py`

## Acceptance

- [ ] Move dataclass, Pydantic, TypedDict, shared import-planning, and stale-plan converter coverage into the focused module without changing behavior.
- [ ] Remove converter-only imports and helpers from the mixed-purpose module; do not duplicate tests.
- [ ] Run the focused module plus `just ci`.

## Evidence

- `tests/unit/test_refactoring_tools.py` is 2,016 lines; formatter changes in its converter coverage currently mix with unrelated rename, format, lint, superclass, and extract-class tests.
