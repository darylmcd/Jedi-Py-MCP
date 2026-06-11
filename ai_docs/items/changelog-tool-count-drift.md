# changelog-tool-count-drift — CHANGELOG narrates 89 tools; live server registers 91

**row:** `changelog-tool-count-drift` · **pri:** `Low` · **size:** `S`

## Anchors

- `CHANGELOG.md` (`[Unreleased]` — only file edited)

Read-only inputs (not edited): `src/python_refactor_mcp/server.py` (live `@mcp.tool` count), `tests/unit/test_server.py` (asserts `== 91`).

## Acceptance

- [ ] The two unbumped tool additions identified.
- [ ] CHANGELOG narrative count aligned with the live 91-tool surface (or baseline corrected).

## Evidence

- Observed during 2026-05-28 backlog-sweep wave-1 reconcile: CHANGELOG says `format_code` 87→88, `apply_lint_fixes` 88→89, but server registers 91 and `test_server.py` asserts 91 — a 2-tool narrative gap.
