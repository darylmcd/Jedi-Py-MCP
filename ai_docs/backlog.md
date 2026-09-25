# Backlog

<!-- purpose: Open work only. Slim-index format — triage in the table, implementation detail in items/<id>.md. Sync rows on ship. -->
<!-- scope: in-repo -->

**updated_at:** 2026-09-25T03:53:55Z
<!-- 2026-06-19: shipped cand-server-status, cand-security-autofix, changelog-tool-count-drift, cand-structural-replace (+RCE fix), change_signature annotation restore. -->
<!-- 2026-07-08: doc-audit filed 2 new rows (backend-fallback-swallowed-exceptions, dead-code-symbol-scan-silent-drop); Refs updated for the 20260527T205134Z plan archival. -->

<!-- Replace the updated_at value above with a FULL ISO 8601 datetime on every change.
     Date-only values (2026-01-01) are INVALID — they invite placeholder drift. -->

## Agent contract

| | |
|---|---|
| **Scope** | This file lists unfinished work only. It is not a changelog. |
| **MUST** | Remove or update backlog rows when work ships; do it in the same PR or an immediate follow-up. Closing a row also deletes its `ai_docs/items/<id>.md` — use `/close-backlog-rows`, which does both atomically. |
| **MUST** | End implementation plans with a final todo: `backlog: sync ai_docs/backlog.md`. |
| **MUST** | Use stable, kebab-case `id` values per open row. |
| **MUST** | Keep the `do` cell **slim** — a bold title + one concrete next deliverable + `[type: …]` + `[source: …]` tags (≤~250 chars). Enough to triage, not to implement. |
| **MUST** | Spill implementation detail (`Anchors:`, acceptance criteria, long-form evidence) to `ai_docs/items/<id>.md` for any **code-touching row**, and point the `detail` cell at it. Seed it from the doc-audit template at `~/.claude/skills/doc-audit/templates/items.md`. Pure-prose rows (Defer rationale, decision notes) may stay inline with `detail: —`. |
| **MUST** | Set `size` per row: `S` (≤1 prod file) / `M` (2–4 prod files) / `L` (>4 prod files or >1 regression shape). `L` is a **split-candidate** — split it into per-slice children before planning against it. >3 test files is also a split-candidate. |
| **MUST** | Keep `deps` to backlog row ids or `—` (`none` ≡ `—`). A dep id matching a live open row = this row is blocked; an id absent from the backlog = satisfied (open-work-only). |
| **MUST NOT** | Add `Completed`, `Shipped`, `Done`, `History`, or `Changelog` sections. Git is the archive. |
| **MUST NOT** | Leave done items in the open table. |
| **MUST NOT** | Inline `Anchors:`/acceptance/multi-line evidence in a code-touching row's `do` cell, or add `### <id>` body sections per item. The slim row + its `items/<id>.md` are the canonical pair. |

## Standing rules

<!-- Ongoing practices, not deletable work items. -->

- **Reprioritize on each audit pass.** Stale priority order is a finding.
- **Keep rows planner-ready.** A row is ready when an agent can read it cold and start a plan: a clear title + next deliverable in the `do` cell, the live anchors in `items/<id>.md`.
- **Replace stale umbrella rows with concrete follow-ons** before planning against them.
- **Detail lives in `items/<id>.md`, evidence in referenced reports** — not in this file. The `do` cell carries the title + next step only; the detail file carries anchors + acceptance + a one-line evidence summary plus the report path.
- **Weak-evidence flag.** When a row's signal is thin (single retro session, self-audit only, etc.) say so explicitly in the `do` cell ("Weaker evidence — N until external session reproduces").
- **Priority tiers:** Critical > High > Medium > Low > Defer.
- Best-practices reference: `ai_docs/references/mcp_best_practices/README.md`.
- See `workflow.md` → **Backlog closure** for close-in-PR expectations.

---

## Critical

<!-- Production-breaking or blocking work. Empty section is fine; keep the header. -->

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|

## High

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `bl-0034` | High | — | **Pyright position/file preflight reported as backend outage** — raise `ToolInputError` for out-of-range line/character and a nonexistent `file_path` in `_validate_position`/`ensure_file_open`. [type: bug] [source: bl-0003] | S | items/bl-0034.md |
| `bl-0035` | High | — | **Rope change-stack/history/transaction misuse reported as backend outage** — raise `ToolInputError` for empty/malformed transactions, empty undo/redo history and stack begin/commit/rollback misuse. [type: bug] [source: bl-0003] | M | items/bl-0035.md |
| `bl-0044` | High | — | Stop RopeBackend.initialize AutoImport pre-warm from spawning a CPU-wide ProcessPoolExecutor (rope generate_cache) that orphans ~24 spawn workers per server when the MCP server is killed; make it lazy or in-process, add regression test. [type: bug] [source: process-sweep 2026-09-24] | S | items/bl-0044.md |

## Medium

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `bl-0009` | Medium | bl-0001 | **Dead-code sweeps exceed 30 s cold** — bound or remove the per-file 2 s diagnostics wait in `dead_code_detection` Phase 1 and re-measure cold time (request count is not the lever — see profile). [type: perf] [source: mcp-surface-audit-20260923] | M | items/bl-0009.md |
| `bl-0025` | Medium | — | **Unhandled-method replies still read as empty results** — route the 5 remaining unhandled-method `return []` branches through `LspFeatureUnsupportedError` (bl-0005's pattern). [type: bug] [source: backlog-remediate-20260924T131340Z] | S | items/bl-0025.md |
| `bl-0036` | Medium | bl-0035 | **Rope caller-argument validation raises RopeError** — raise `ToolInputError` for bad positions/offsets, out-of-workspace paths, missing `change_signature` op args and invalid `split_module` targets. [type: bug] [source: bl-0003] | S | items/bl-0036.md |
| `bl-0037` | Medium | — | **Search/analysis caller-input ValueErrors skip [INVALID_INPUT]** — convert the plain `ValueError` input checks in structural, search helpers, diagnostics and type_users to `ToolInputError`. [type: bug] [source: bl-0003] | M | items/bl-0037.md |
| `bl-0038` | Medium | — | **Navigation/rename/server caller-input ValueErrors skip [INVALID_INPUT]** — convert the plain `ValueError` input checks in hierarchy, outline, rename and server to `ToolInputError`. [type: bug] [source: bl-0003] | M | items/bl-0038.md |
| `bl-0039` | Medium | — | **Pyright restart-retry leaks a raw TimeoutError** — wrap the post-restart `wait_for` retry in `_request` so its timeout raises `PyrightError` like the first attempt; add a unit test. [type: bug] [source: backlog-remediate-20260924T183010Z] | S | items/bl-0039.md |

## Low

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `bl-0018` | Low | bl-0035 | **Numeric bounds inconsistent across tools** — apply one validation rule for `limit`/`offset`/`depth`/`max_items`/`count` (≥1 or ≥0) uniformly, and reject `undo`/`redo` `count < 1`. [type: bug] [source: mcp-surface-audit-20260923] | M | items/bl-0018.md |
| `bl-0021` | Low | bl-0020 | **Closed-set tool params expose no enum or bounds** — type `direction`/`style`/`kind`/`severity_filter`/`source`/`language`/`SignatureOperation.op` as `Literal`, add `ge=0` to line/character positions; contract test checks the schema. [type: bug] [source: bl-0017] | M | items/bl-0021.md |
| `bl-0022` | Low | bl-0021 | **Tools silently accept unknown argument keys** — BLOCKED: operator contract-care decision (Directive #4, PUBLIC repo) first; then emit `additionalProperties: false` and a typed `refactor_transaction` step model. [type: bug] [source: bl-0017] | M | items/bl-0022.md |
| `bl-0040` | Low | — | **`_validate_position` rejects valid UTF-16 end-of-line columns** — bound `character` by the line's UTF-16 length using bl-0033's helpers. [type: bug] [source: backlog-remediate-20260924T183010Z] | S | items/bl-0040.md |
| `bl-0041` | Low | — | **Relative path params resolve against the server cwd** — decide workspace-relative vs reject for relative `file_path`/`root_path` in `validate_workspace_path` and pin it with a test. [type: bug] [source: backlog-remediate-20260924T183010Z] | S | items/bl-0041.md |
| `bl-0042` | Low | bl-0041 | **Workspace-relative directory resolution duplicated** — share one `util/shared.py` helper between `tool_runtime` DIR_PARAMS and `type_stubs._resolve_stub_root`. [type: refactor] [source: backlog-remediate-20260924T183010Z] | M | items/bl-0042.md |
| `bl-0043` | Low | — | **`.ai-doc-audit.md` stale consumption path and `private` note** — say the servers are registered user-scope in `~/.claude.json` and drop the `private` block wording. [type: docs] [source: backlog-remediate-20260924T183010Z] | S | items/bl-0043.md |

## Defer

<!-- Explicitly parked. Record WHY in the `do` cell. -->

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `cand-find-cyclic-imports` | Defer | — | **Dedicated cycle report — parked as redundant** — `get_module_dependencies` already returns cycles; unblock only if per-edge provenance (file:line:col per import) is added as a real delta. [type: enhancement] [source: candidate-proposal] | S | items/cand-find-cyclic-imports.md |
| `rope-python314-deprecations` | Defer | — | **Rope Python 3.14 deprecations — parked upstream** — latest 1.14.0 emits project, AutoImport UTC, and libutils warnings; unblock on an upstream release or API-removal deadline. [type: reliability] [source: session-20260829] | M | items/rope-python314-deprecations.md |

## Refs

- `ai_docs/workflow.md` — execution flow and backlog closure rules
- `ai_docs/architecture.md` — current system architecture
- `ai_docs/items/` — per-row implementation detail (Anchors/Acceptance/Evidence); seed new files from `~/.claude/skills/doc-audit/templates/items.md`
- `ai_docs/references/mcp_best_practices/README.md` — MCP design reference
- `CI_POLICY.md` — merge gating policy
- `audit-reports/application-brainstorm.md` — not-yet-sized product/refactor ideas (BRAIN-001..022 as of Pass 6, 2026-06-19) for brainstorm/planning intake; promote a BRAIN row to a sized backlog row when its first slice is ready
- `ai_docs/archive/plans/20260527T205134Z_backlog-sweep/plan.md` — Backlog sweep (20260527T205134Z), completed 2026-05-29, archived 2026-07-08 (30+ days stable). Shipped 6 initiatives across 6 PRs (#50, #51, #52, #57, #58, #59); closed 6 backlog rows.
- `ai_docs/archive/plans/20260620T020942Z_top-n-remediation/plan.md` — Top-N remediation (20260620T020942Z), completed 2026-06-20, archived 2026-08-30 (30+ days stable). Shipped 4 Medium rows across PRs #69-#72; `mypy-2x-migration` rerouted to `/backlog-sweep:prepare`.
- `ai_docs/archive/plans/20260620T215105Z_backlog-sweep/plan.md` — Backlog sweep (20260620T215105Z), completed 2026-06-20, archived 2026-08-30 (30+ days stable). 1 initiative, merged.
