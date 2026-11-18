# sanctioned-roots-core — Sanctioned-root set, path check and SANCTIONED_ROOT error (piece A)

**row:** `sanctioned-roots-core` · **pri:** `Medium` · **size:** `M` · **verified:** `102c7e0efba2ffe588c84366741d7e9de10eb546`

## Anchors

- `src/python_refactor_mcp/config.py`
- `src/python_refactor_mcp/errors.py:38`
- `src/python_refactor_mcp/util/shared.py:173`
- `docs/setup.md`

## Acceptance

- [ ] Setting parsed with os.pathsep; "." resolves against the startup directory (test from outside the project); a missing or non-directory entry is a startup error naming the setting; empty means denied.
- [ ] One function decides containment: links and junctions followed, case-insensitive on Windows, whole-component match, identical result for existing and missing paths, UNC refused first (ADR 0011).
- [ ] [SANCTIONED_ROOT] error with the two path-free messages of the ADR (not configured / outside the roots), distinct from INVALID_INPUT.
- [ ] docs/setup.md example config sets "." explicitly; changed-breaking fragment only if behaviour changes (it does not in this piece: maintenance- or added-).
- [ ] ADR 0015 (docs/adr/0015-sanctioned-root-boundary.md), section Tests, is the test list; every test is red on main before the piece. Tests for A: ".", link escape, case and prefix, message text.

## Evidence

- Operator-approved ADR 0015 (2026-11-18). Replaces the four BLOCKED rows multi-project-rename-roots, workspace-selection-authorized-roots, output-dir-anchorless-boundary, implicit-workspace-unlocked-window.
