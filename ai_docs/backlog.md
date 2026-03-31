# Backlog

Open follow-up items only. Remove entries once verified complete.
Ordered by severity: P0 (bug fixes / security) > P1 (usability / hardening) > P2 (new features) > P3 (advanced) > P4 (stretch) > Tests/Docs.

Best practices analysis: `ai_docs/mcp_best_practices.md`.
Historical plans, audits, and reports removed — all open items consolidated here; originals preserved in git history.

---

## P3 — Known Limitations

- Status: `documented`
  Area: upstream limitation
  Item: `change_signature` strips Python 3 type annotations during normalization. This is a known rope limitation (`ArgumentNormalizer`). Documented in rope_backend.py docstring.
  Source: mcp-server-audit-report #15 (2026-03-28)

---

## Tests & Documentation

- Status: `open`
  Area: documentation
  Item: Complete prompt example bank coverage for all tools in `ai_docs/domains/python-refactor/mcp-checklist.md`.

