# Plan review — 20260924T183010Z_backlog-remediate

Cold `plan-reviewer-adversarial`, two cycles.

## Cycle 0 — failed (block 1, warn 7, info 10)

- block bl-0025 (Rule 5b): `fanoutEstimate` null with a concrete caller probe; pinned Pyright lacks typeHierarchy/foldingRange capabilities, so the guard would break two tools and two integration assertions.
- warns: stored conflict graph empty; hotspot adjacencies 3-4, 4-5, 8-9; bl-0019/bl-0020 wave conflict; bl-0020 Rule 3b (bulk retype declared edit-only).
- infos remediated: bl-0020 drift-lock contradiction + stale anchor; bl-0009 unconditional close; bl-0019 "Non-destructive" docstring; bl-0028 conditional `_imports.py`; bl-0032 doc-audit class flip.

## Cycle 1 — failed (block 1, warn 6, info 5)

- block bl-0025 (Rule 3, introduced by remediation): raising `LspFeatureUnsupportedError` in `get_folding_ranges` bypasses the existing AST fallback at `tools/navigation/outline.py:274-276`; `outline.py` missing from Scope.
- Disposition: bl-0025 **deferred** (still blocked after one remediation cycle); re-plan note appended to `items/bl-0025.md`.
- warn bl-0009 (items file outside Scope): resolved — the note is written by the orchestrator in the reconcile PR.
- Accepted open warns: bl-0020 Rule 3b; bl-0019/bl-0020 C2-wave-conflict + hotspot (serialized by `generations` into separate generations; per-PR current-main `just ci` gate).
- Tooling note (global): legacy-inline stanzas over 5120 B (bl-0009, bl-0020, bl-0023, bl-0030) are accepted by `stanza-merge` though file-mode execute rejects >5120 B.
