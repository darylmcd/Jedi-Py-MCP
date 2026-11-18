# sanctioned-roots-output-dir — output_dir sanctioned-root check on top of workspace confinement (piece D)

**row:** `sanctioned-roots-output-dir` · **pri:** `Low` · **size:** `M` · **verified:** `102c7e0efba2ffe588c84366741d7e9de10eb546` · **deps:** `sanctioned-roots-workspace-selection`

## Anchors

- `src/python_refactor_mcp/util/shared.py:195`
- `src/python_refactor_mcp/tool_runtime.py:334`

## Acceptance

- [ ] A relative output_dir climbing out of the workspace is refused (test).
- [ ] An absolute output_dir inside the roots but outside the call workspace is refused (test).
- [ ] An absolute output_dir with no workspace determinable is refused, no fallback (test).
- [ ] Not a loosening: no currently accepted output_dir is refused except by the new root check; fixed- or changed-breaking- fragment as the diff warrants.
- [ ] ADR 0015 (docs/adr/0015-sanctioned-root-boundary.md), section Tests, is the test list; every test is red on main before the piece.

## Evidence

- ADR 0015 answer 3 as amended by ruling 1 (confinement already existed; supersedes output-dir-anchorless-boundary).
