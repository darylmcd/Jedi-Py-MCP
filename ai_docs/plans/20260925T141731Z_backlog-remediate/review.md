# Plan review: 20260925T141731Z_backlog-remediate (cycle 0)

- **Stanza source:** legacy-inline in `plan.md`; all 12 bodies ≤ 5,120 bytes.
- **Schema:** 4. **Outcome:** passed-with-warnings (block 0, warn 8, info 9). **Anchor verification:** performed (bl-0034/35/44 fully; the rest spot-checked; bl-0035 drift 1-2 lines).

## Summary

12 pending initiatives, each closing at most one row (bl-0009 closes none — declared partial slice). No Rule 1 bundles; all estimates ≤ 55K (< 80K marker); no `dependsOn` edges; no Rule 5b under-count.

## Findings

| Initiative | Severity | Rule | Evidence | Orchestrator resolution |
|---|---|---|---|---|
| plan | warn | C2-graph-disagreement | Stored `conflictGraph.edges` empty; rebuild gives 14 edges. | `generations --persist`; 5 generations separate every shared pair. |
| bl-0044 | warn | C2-wave-conflict | Orders 2/3 share `rope_backend.py` + `test_rope_backend.py`. | Gen 1 vs gen 2. |
| bl-0025 | warn | C2-wave-conflict | Orders 4/5 share `pyright_lsp.py` + `test_pyright_lsp.py`. | Gen 2 vs gen 3. |
| bl-0044 | warn | hotspot | Orders 2/3 both touch `rope_backend.py`. | Different generations. |
| bl-0025 | warn | hotspot | Orders 4/5 both touch `pyright_lsp.py`. | Different generations. |
| bl-0009 | warn | 3 | Batch return type lacks a per-file error channel (`dead_code.py:119-133`); P1/P2 overlap loses Phase 2 overwrite precedence (`:135-140` vs `:164-170`); step (0) had no abort branch. | Stanza amended: per-file failure map, P1 merged before P2, explicit ABORT → `held`; detail-file update moved to reconcile. |
| bl-0021 | warn | 3 | Closes the row with Acceptance bullet 1 (`source`) unmet. | Backlog sync records the amendment; PR body states it. |
| bl-0041 | warn | 3 | Rejects all `PATH_PARAMS`; absolute contract documented for only 4 (`source_path`, `destination_file`, `destination_package` bare `str`). | Stanza amended: described aliases + retype (Scope 4 files); breaking callout lists 7 params; changelog prefix fixed. |
| bl-0034, bl-0009, bl-0025, bl-0038, bl-0039, bl-0040 | info | C2 | Degree ≥ 2 without `heroic-last`. | — |
| plan | info | hotspot | Six consecutive pairs touch different hotspots, no shared file. | — |
| bl-0044 | info | anchor | First `autoimport_search` now indexes in-process under the 30 s rope timeout — new exposure on large workspaces. | Carried to executor/reviewer. |
| plan | info | anchor | Anchors resolve at `352eaa5`. | — |

## Outside-rubric observations

- bl-0041 changelog draft lacked the `- **Changed — BREAKING:** ` prefix (`scripts/changelog_fragments.py:84-87`) — fixed.
- bl-0041: on Windows `Path("/x").is_absolute()` is False — pinned in a test per amended stanza.
- bl-0021 leaves `hierarchy.py` `_TYPE_DIRECTION_ALIASES` and `strip().lower()` normalization unreachable from MCP — follow-on row owed at closeout (Directive #3).
