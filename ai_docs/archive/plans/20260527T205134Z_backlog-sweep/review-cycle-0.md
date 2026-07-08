# Plan review — 2026-05-27T20:51:34Z (cycle 0)

**Plan reviewed:** C:/Code-Repo/Jedi-Py-MCP/ai_docs/plans/20260527T205134Z_backlog-sweep/
**Reviewer mode:** /backlog-sweep:prepare (Phase D)
**Cycle:** 0
**Outcome:** passed-with-warnings
**Initiative count:** 6 pending
**Findings:** block: 0, warn: 2, info: 5
**Anchor verification:** performed (spot-checked initiatives 1–3 + I6 rewritten anchor)

## Summary

Plan is structurally sound — all six initiatives satisfy Rules 1, 3, 3b, 4, 5, and 5b. Anchor citations for the first three initiatives verify cleanly (server.py: 1815 lines, 91 @mcp.tool registrations; rope_backend: 30 wait_for occurrences; jedi_backend: 17; pyright_lsp.py: 1427 lines with get_hover at line 511 matching cited pattern). I6's stale anchor (`call_hierarchy.py` → `hierarchy.py`) was correctly rewritten in the Diagnosis. The reviewer-computed conflict graph exactly matches the orchestrator's (6 edges, all on server.py, degrees {1:3, 2:0, 3:0, 4:3, 5:3, 6:3}; zero-degree: [2, 3]). Primary concerns are scheduling: order pairs (4,5) and (5,6) are adjacent AND share server.py — Step 6 sort should have separated them. Initiatives 1, 4, 5, 6 collectively form a 4-clique on server.py; expect serial scheduling across waves.

## Findings

| Initiative | Severity | Rule | Evidence |
|---|---|---|---|
| cand-unused-symbol-sweep / cand-extract-superclass | warn | C2-wave-conflict | Adjacent-order initiatives 4 and 5 share file src/python_refactor_mcp/server.py; planner Step 6 should have separated them. |
| cand-extract-superclass / cand-test-impact-selector | warn | C2-wave-conflict | Adjacent-order initiatives 5 and 6 share file src/python_refactor_mcp/server.py; planner Step 6 should have separated them. |
| server-tool-registration-table | info | C2-wave-conflict | Initiative conflicts with 3 peers on server.py; expect serial scheduling. |
| cand-unused-symbol-sweep | info | C2-wave-conflict | Initiative conflicts with 3 peers on server.py; expect serial scheduling. |
| cand-extract-superclass | info | C2-wave-conflict | Initiative conflicts with 3 peers on server.py; expect serial scheduling. |
| cand-test-impact-selector | info | C2-wave-conflict | Initiative conflicts with 3 peers on server.py; expect serial scheduling. |
| cand-test-impact-selector | info | anchor-stale | Original backlog anchor `tools/navigation/call_hierarchy.py` does not exist; plan correctly rewrites to `hierarchy.py` in Diagnosis. |

## Conflict graph

(Reviewer-computed; agreement with orchestrator: yes — exact edge-set match.)

```json
{
  "edges": [
    {"a": 1, "b": 4, "sharedFiles": ["src/python_refactor_mcp/server.py"]},
    {"a": 1, "b": 5, "sharedFiles": ["src/python_refactor_mcp/server.py"]},
    {"a": 1, "b": 6, "sharedFiles": ["src/python_refactor_mcp/server.py"]},
    {"a": 4, "b": 5, "sharedFiles": ["src/python_refactor_mcp/server.py"]},
    {"a": 4, "b": 6, "sharedFiles": ["src/python_refactor_mcp/server.py"]},
    {"a": 5, "b": 6, "sharedFiles": ["src/python_refactor_mcp/server.py"]}
  ],
  "degrees": {"1": 3, "2": 0, "3": 0, "4": 3, "5": 3, "6": 3},
  "zeroDegreeInitiatives": [2, 3]
}
```

## Hotspot scheduling

No addenda loaded — no hotspot list to enforce. However, server.py is an organic hotspot (4 of 6 initiatives touch it). Recommend executor parallel-mode planner serializes the 1/4/5/6 clique.

## Stale-row spot check

All six selected row ids present in current backlog.

## Recommended next step

Proceed to Phase F (handoff-readiness) then `/backlog-sweep:execute`. Surface the two adjacent-order wave conflicts in the execute run summary so parallel-mode planner separates initiatives 4↔5 and 5↔6 into different waves. The server.py 4-clique forces serial scheduling regardless.
