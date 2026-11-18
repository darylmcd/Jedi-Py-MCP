# sanctioned-roots-multi-project-rename — multi_project_rename write guard (piece B, the live write risk)

**row:** `sanctioned-roots-multi-project-rename` · **pri:** `Medium` · **size:** `M` · **verified:** `102c7e0efba2ffe588c84366741d7e9de10eb546` · **deps:** `sanctioned-roots-core`

## Anchors

- `src/python_refactor_mcp/tool_runtime.py:61`
- `src/python_refactor_mcp/backends/rope_backend.py:2083`
- `tests/unit/test_error_boundary.py`

## Acceptance

- [ ] additional_roots outside every sanctioned root with apply=true: refused with SANCTIONED_ROOT, no Project opened, no file opened or written (test).
- [ ] A changed path outside the roots at apply time is refused and nothing is written (test).
- [ ] additional_roots is removed from _PATH_LIKE_ALLOWLIST in tests/unit/test_error_boundary.py.
- [ ] changed-breaking-* fragment and PR-body callout; migration note per ADR 0015.
- [ ] ADR 0015 (docs/adr/0015-sanctioned-root-boundary.md), section Tests, is the test list; every test is red on main before the piece.

## Evidence

- ADR 0015 answer 1. multi_project_rename opens and writes in client-supplied roots with no authorization check (supersedes row multi-project-rename-roots). Take this first after piece A.
