# changelog-unreleased-tool-tally — Fix CHANGELOG [Unreleased] stale tool tally

**row:** `changelog-unreleased-tool-tally` · **pri:** `Low` · **size:** `S`

## Anchors

- `CHANGELOG.md:33` (the [Unreleased] reconciliation line "All now read 96")

## Acceptance

- [ ] The [Unreleased] tool-count reconciliation line reads 97 (matches the live surface), internally consistent with the [Unreleased] Added entries (server_status 95→96, structural_replace 96→97).

## Evidence

- work-search discovery-sweep (2026-06-19): reconciliation line says "All now read 96" while the Added entries above reach 97; README/test_server.py:14/reference.md all read 97 at HEAD 62f7d39. Distinct from the CLOSED `changelog-tool-count-drift` (#64, which was README/.ai-doc-audit saying 91).

## Context

- Trivial one-line docs fix — an operator may prefer to bump the line inline rather than route through a planning flow.
