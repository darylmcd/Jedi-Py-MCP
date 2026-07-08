# Plan review — 2026-05-28T18:38:30Z (cycle 1)

**Plan reviewed:** C:/Code-Repo/Jedi-Py-MCP/ai_docs/plans/20260527T205134Z_backlog-sweep/
**Reviewer mode:** /backlog-sweep:prepare (Phase D)
**Cycle:** 1
**Outcome:** passed-with-warnings
**Initiative count:** 3 pending (4, 5, 6; initiatives 1–3 merged — context only)
**Findings:** block: 0, warn: 2, info: 4
**Anchor verification:** performed (initiatives 4/5/6 — all cited anchors resolve against the post-#52 tree)

## Summary

Re-review of the post-#52 re-prepare. The three pending initiatives (4 cand-unused-symbol-sweep, 5 cand-extract-superclass, 6 cand-test-impact-selector) were regenerated after PR #52 moved per-tool registration out of `server.py` into the `tool_registry.py` `TOOL_RECORDS` table. I independently verified the current tree: `tool_registry.py` holds 83 `ToolRecord` entries + `register_tools(mcp)` (called at `server.py:294`); `server.py` retains exactly 8 explicit `@mcp.tool` wrappers; 83 + 8 = 91, matching `tests/unit/test_server.py:14`. All three stanzas correctly target the `TOOL_RECORDS` table + a pure-delegation `async def` (NOT stale server.py wrapper coordinates) — the remediation did exactly what was required. Every cited anchor resolves: `dead_code.py:49/63/161`, `cst_apply.py:58/95`, `hierarchy.py:107/36`, `test_map.py:60-63`, and the `tool_registry.py` delegate shape (`dead_code_detection` at :935) plus its `PaginatedDeadCode`/`RefactorResult` imports. The stale `call_hierarchy.py` anchor is correctly rewritten to `hierarchy.py` in initiative 6's Diagnosis. Rules 1/3/4/5/3b all hold (init 6 is at the Rule-3 hard cap of 4 production files but does not exceed it). The reviewer-computed conflict graph matches the orchestrator's exactly: pending 4/5/6 form a mutual clique sharing `tool_registry.py` (and the `test_server.py` count-bump line), forcing strictly-serial scheduling — the pre-#52 `server.py` clique is correctly superseded. Re-review delta: prior block count 0 → current 0; no oscillation, no regression introduced by remediation. The two warns are adjacent-order wave conflicts on the 4/5/6 clique — the same serial-scheduling reality, now correctly attributed to `tool_registry.py`.

## Findings

| Initiative | Severity | Rule | Evidence |
|---|---|---|---|
| cand-unused-symbol-sweep / cand-extract-superclass | warn | C2-wave-conflict | Adjacent-order initiatives 4 and 5 share file src/python_refactor_mcp/tool_registry.py (+ tests/unit/test_server.py count bump); planner Step 6 should have separated them. |
| cand-extract-superclass / cand-test-impact-selector | warn | C2-wave-conflict | Adjacent-order initiatives 5 and 6 share file src/python_refactor_mcp/tool_registry.py (+ tests/unit/test_server.py count bump); planner Step 6 should have separated them. |
| cand-unused-symbol-sweep | info | C2-wave-conflict | Initiative conflicts with 2 peers on tool_registry.py; expect serial scheduling. |
| cand-extract-superclass | info | C2-wave-conflict | Initiative conflicts with 2 peers on tool_registry.py; expect serial scheduling. |
| cand-test-impact-selector | info | C2-wave-conflict | Initiative conflicts with 2 peers on tool_registry.py; expect serial scheduling. |
| cand-extract-superclass | info | 5b | fanoutEstimate null and Approach performs CST base-class member-hoist; skip is justified (new tool, zero existing inbound callers — verified: no extract_superclass symbol under src/), but the base-class-extraction keyword is borderline against the fanout-probe trigger list. |

## Conflict graph

(Reviewer-computed; agreement with orchestrator: yes — exact edge-set match. Initiatives 1–3 merged, degree 0, not schedulable. Pending 4/5/6 share tool_registry.py; the pre-#52 server.py clique no longer applies.)

```json
{
  "edges": [
    {"a": 4, "b": 5, "sharedFiles": ["src/python_refactor_mcp/tool_registry.py", "tests/unit/test_server.py"]},
    {"a": 4, "b": 6, "sharedFiles": ["src/python_refactor_mcp/tool_registry.py", "tests/unit/test_server.py"]},
    {"a": 5, "b": 6, "sharedFiles": ["src/python_refactor_mcp/tool_registry.py", "tests/unit/test_server.py"]}
  ],
  "degrees": {"1": 0, "2": 0, "3": 0, "4": 2, "5": 2, "6": 2},
  "zeroDegreeInitiatives": []
}
```

## Hotspot scheduling

| Hotspot | Initiatives | Adjacent? |
|---|---|---|
| (none — no addenda loaded) | — | — |

No addenda → no hotspot list to enforce. Note: `tool_registry.py` is now the organic shared surface (all 3 pending initiatives append a ToolRecord + bump the same `test_server.py:14` assertion 91→92→93→94). Executor must serialize 4/5/6 regardless of wave mode.

## Stale-row spot check

| Row id | Present? |
|---|---|
| cand-unused-symbol-sweep | yes (backlog.md:68) |
| cand-extract-superclass | yes (backlog.md:67) |
| cand-test-impact-selector | yes (backlog.md:69 — backlog row still cites stale call_hierarchy.py anchor; plan Diagnosis correctly rewrites to hierarchy.py) |

## Recommended next step

Proceed to Phase F (handoff-readiness) then `/backlog-sweep:execute`. Surface the two adjacent-order wave conflicts (4↔5, 5↔6) in the run summary; the 4/5/6 mutual clique on `tool_registry.py` forces strictly-serial scheduling — there is no parallel wave possible among the three. Each lands a sequential count bump (91→92→93→94), so order matters: the second and third executors must rebase on the prior count.
