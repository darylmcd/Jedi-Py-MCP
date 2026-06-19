# tool-position-base-convention-docs — Document 0-based line/character in position-based tool descriptions

**row:** `tool-position-base-convention-docs` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tool_registry.py:118` (TOOL_RECORDS descriptions for position-based tools — representative `find_references`)
- `src/python_refactor_mcp/server.py` (explicit `@mcp.tool` wrappers taking line/character)
- `src/python_refactor_mcp/models.py:9` (`Position` already documents "0-based line and character offset" — canonical phrase source)

(Regression test in `tests/unit/test_server.py` — see Acceptance.)

## Acceptance

- [ ] Every tool taking line/character states the 0-based convention (shared phrase, e.g. "Positions are 0-based (LSP convention).").
- [ ] A test asserts the convention phrase appears in each position-based tool description (mirrors the existing tool-count-drift gate).

## Evidence

- ui-ux discovery-sweep (2026-06-19): ~60+ position-based tool descriptions never state the 0-based convention; only `inline_parameter` does, and a 1-based guess fails silently (empty result). See `ai_docs/audits/20260619-2130/02_mcp_tools.md`.

## Context

- Pairs with `pyright-position-out-of-range-guard` (the behavioural half — silent empty on bad coordinates). Both harden the position interface; can be implemented together.
