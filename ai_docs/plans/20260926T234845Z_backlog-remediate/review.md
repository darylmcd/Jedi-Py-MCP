# Plan review — 20260926T234845Z_backlog-remediate (cycle 0)

- Plan dir: `C:/Code-Repo/Jedi-Py-MCP/.worktrees/plan-20260926T234845Z_backlog-remediate/ai_docs/plans/20260926T234845Z_backlog-remediate/`
- Stanza storage: legacy-inline (`plan/` absent, ENOENT); every stanza under 5120 bytes (max 5035, bl-0045)
- Schema: 4 (accepted)
- Outcome: **passed-with-warnings**
- Counts: block 0 · warn 7 · info 9
- Anchor verification: **performed** (bl-0009, bl-0036, bl-0045; all cited file:line resolve at 814b922)
- Rules source: `~/.claude/prompts/backlog-remediate-rules.md` (sha256 47cbf122…598f29, read in full)

## Summary

The plan has no blocking findings. The deps graph is empty and acyclic, every row is still open, each initiative closes 1 row, all token estimates are under the 80K marker, and no fanout undercount or null probe was found. Warnings: (1) the stored conflict graph is empty, but the Scope file lists produce 3 edges; (2) three consecutive-order pairs touch addenda hotspots; (3) bl-0045 cites tool-surface-only as the reason tool_registry.py is a companion, and that shape does not force the file (its other cited shapes check out against live source); (4) bl-0046 closes its row while deferring same-root-cause rope sites to "notes" that do not exist, with no tracking row; (5) bl-0042's token estimate is below its band. The bl-0009 reframe is legitimate, with a condition: the stanza still ships the row's prescribed prewarm lever (scoped to targets) and ties to acceptance bullet 2, but the row may close only if the PR-recorded re-measurement meets the Validation thresholds. Several stanzas' Risks misstate sibling file overlaps. Execute uses the recomputed graph, so this is harmless, but the text is inaccurate.

## Findings

| Initiative | Severity | Rule | Evidence |
|---|---|---|---|
| plan | warn | C2-graph-disagreement | stored edges [] ; computed 1-6 {tests/unit/test_search_tools.py}, 3-5 {src/python_refactor_mcp/util/shared.py}, 3-6 {tools/analysis/diagnostics.py, tests/unit/test_analysis_tools.py} |
| bl-0045 | warn | hotspot | orders 2->3: bl-0036 rope_backend.py / bl-0045 pyright_lsp.py, tool_registry.py |
| bl-0018 | warn | hotspot | orders 3->4: bl-0045 pyright_lsp.py, tool_registry.py / bl-0018 server.py |
| bl-0042 | warn | hotspot | orders 4->5: bl-0018 server.py / bl-0042 tool_runtime.py |
| bl-0045 | warn | 3 | 5 prod files. tool_registry.py is justified as tool-surface-only, but that shape narrows a whole initiative and does not force a companion; no gate or defect forces the :316-327 description/log edit, and dropping it gives 4 files. The other shapes hold on live source: shared.py is defect-forced (pyright_lsp.py:545-547 raise -> util/shared.py:78 -> refactoring/helpers.py:131 -> 20+ post_apply_diagnostics callers, so an applied edit would be reported as a tool error), and docs/tool-reference.md is gate-forced (test_doc_tool_count_drift.py:220-247 renders the live annotation; docs:20 shows Paginated[DiagnosticSummary]) |
| bl-0046 | warn | 3 | Diagnosis names same-shape sites rope_backend.py:167, :190, :1154. Scope defers them to "bl-0036 or a spin-off row (see notes)", but state notes is null, bl-0036 does not include them, and no row is cited. Acceptance bullet 1 ends up partially met with an untracked residual (Directive #1/#3) |
| bl-0042 | warn | 5 | 20000 tokens for 3 prod + 1 test file, below the "fix 3-4 files ~40-60K" band |
| bl-0045 | info | C2 | degree 2 (orders 5, 6) without heroic-last |
| bl-0046 | info | C2 | degree 2 (orders 1, 3) without heroic-last |
| bl-0009 | info | 3 | Reframe legitimate: acceptance 1 (<10 s cold) reported met; the stanza ships a target-set prewarm (the row's own lever) plus the cold/warm determinism fix (acceptance 2). Close only if the PR re-measurement meets the thresholds |
| bl-0009 | info | C2 | Risks says "No sibling file overlap", but test_search_tools.py is shared with bl-0046; the Protocol-user list omits constructors.py:102 (no impact) |
| bl-0045 | info | C2 | Risks overlap list is wrong: bl-0018 does not edit shared.py/tool_registry.py and bl-0009 does not edit pyright_lsp.py. The real overlaps are bl-0042 and bl-0046 |
| bl-0042 | info | C2 | Risks says bl-0018 edits util/shared.py; that is false. The real co-editor is bl-0045 |
| bl-0045 | info | 3 | Open conditional ("if Pyright stays silent on excluded files, filter them out") is left to the executor. Separately, notify_file_changed (pyright_lsp.py:504-527) never pops _diagnostics, so post-apply diagnostics can return cached pre-edit results. This is a pre-existing defect and needs its own row |
| bl-0036 | info | 3 | _offset_to_position (rope_backend.py:324) has 0 production callers (only test_rope_backend.py:272), so converting :327/:331 is moot. It is a dead-code row candidate |
| plan | info | anchor | performed; all first-3 anchors resolve |

## Per-initiative rubric walk

| # | id | stale-row | 1 | 3 | 3b | 4 | 5 | 5b | deps |
|---|---|---|---|---|---|---|---|---|---|
| 1 | bl-0009 | open | 1 row | 2 prod ok | edit-only | 1 | 35K ok | fanout 2 <= 4 | [] |
| 2 | bl-0036 | open | 1 row | 1 prod ok | edit-only | 1 | 30K ok | fanout 1 <= 3 | [] |
| 3 | bl-0045 | open | 1 row | 5 prod; warn (tool_registry shape) | edit-only | 3 | 55K ok | fanout 6 <= 7 | [] |
| 4 | bl-0018 | open | 1 row | 2 prod ok | edit-only | 1 | 35K ok | fanout 2 <= 4 (29+5 alias uses verified; only server.py:237 raw) | [] |
| 5 | bl-0042 | open | 1 row | 3 prod ok | edit-only | 1 | 20K warn (low) | fanout 3 <= 5 | [] |
| 6 | bl-0046 | open | 1 row | 4 prod; warn (orphaned residual) | edit-only | 4 test files, one shape -> no finding | 45K ok | fanout 4 <= 6 | [] |

Deps walk (one pass, DFS mirroring assertAcyclicDependsOn): all dependsOn are empty, so there are no cycles and no unknown ids.

## Reviewer-computed conflict graph (agreement: false)

    {"edges": [
      {"a": 1, "b": 6, "sharedFiles": ["tests/unit/test_search_tools.py"]},
      {"a": 3, "b": 5, "sharedFiles": ["src/python_refactor_mcp/util/shared.py"]},
      {"a": 3, "b": 6, "sharedFiles": ["src/python_refactor_mcp/tools/analysis/diagnostics.py", "tests/unit/test_analysis_tools.py"]}],
     "degrees": {"1": 1, "2": 0, "3": 2, "4": 0, "5": 1, "6": 2},
     "zeroDegreeInitiatives": [2, 4]}

No consecutive-order pair shares a file, so there is no C2-wave-conflict.

## Hotspots

| Pair (orders) | Earlier touches | Later touches | Finding |
|---|---|---|---|
| 1->2 | - | rope_backend.py | none |
| 2->3 | rope_backend.py | pyright_lsp.py, tool_registry.py | warn |
| 3->4 | pyright_lsp.py, tool_registry.py | server.py | warn |
| 4->5 | server.py | tool_runtime.py | warn |
| 5->6 | tool_runtime.py | - | none |

## Stale rows

| id | in ai_docs/backlog.md |
|---|---|
| bl-0009 | yes (line 60) |
| bl-0036 | yes (61) |
| bl-0045 | yes (62) |
| bl-0018 | yes (68) |
| bl-0042 | yes (70) |
| bl-0046 | yes (71) |

## Bad code observed (Directive #3; for the orchestrator to file)

| Where | Issue | Suggested row |
|---|---|---|
| backends/pyright_lsp.py:504-527 notify_file_changed | Does not clear _diagnostics (unlike _refresh_if_changed :502), so attach_post_apply_diagnostics can return pre-edit diagnostics | S bug: pop cached diagnostics on notify; test post-apply freshness |
| backends/rope_backend.py:324 _offset_to_position | Production-dead (test-only caller) | S refactor: delete it and its test |
| tools/search/_helpers.py:118 is_test_file | Lets fixture trees under tests/ into sweep targets (bl-0009 deepener observation) | S bug: exclude conventional test dirs |
| rope_backend.py:167/:190/:1154 | Unreachable case folding (bl-0046 residual) | S refactor, or fold into bl-0036/bl-0046 |

## Recommended next step

Proceed (passed-with-warnings). Before execute: run `bsweep-state.mjs generations` to refresh the stored graph. Then either drop tool_registry.py from bl-0045 or re-justify it; file (or cite) a tracking row for the bl-0046 rope residual, or fold it into bl-0036; and bump bl-0042's estimate into band. The Risks overlap prose is optional cleanup.
