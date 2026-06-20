# position-convention-positions-list-tools — extend 0-based convention to Position-wrapped tools

**row:** `position-convention-positions-list-tools` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tool_registry.py` (`selection_range`, `test_impact_select` descriptions — these take caller-supplied positions nested in `Position` objects, e.g. `positions: list[Position]`).
- `tests/unit/test_server.py` (`test_position_based_tools_document_zero_based_convention` — selector keys on `{"line", "start_line"}` only, so `positions`/`Position`-shaped schemas are invisible to it).

## Acceptance

- [ ] `selection_range` (and `test_impact_select`, and any other tool taking `positions: list[Position]` / nested `Position`) descriptions embed `POSITION_CONVENTION_PHRASE` verbatim.
- [ ] The regression selector also matches tools whose input schema carries a `positions`/`Position`-shaped parameter, so those tools are covered — not vacuously skipped — and any future positions-list tool is auto-covered.

## Evidence

- `tool-position-base-convention-docs` (#72) code-quality review (2026-06-20): the shipped gate's `{line, start_line}` selector cannot see `positions: list[Position]` schemas. Live surface: 98 tools, 40 selected; `selection_range` excluded and undocumented while both unit tests pass green (vacuous skip). The `Position` model's own description already documents the convention, so callers are not wholly uninformed — this row closes the description + gate gap.

## Context

- Follow-up slice to `tool-position-base-convention-docs` (#72), which intentionally scoped to bare `line`/`character` tools. The shared `POSITION_CONVENTION_PHRASE` constant already exists in `tests/unit/test_server.py`.
