# Backlog

<!-- purpose: Open work only. Slim-index format — triage in the table, implementation detail in items/<id>.md. Sync rows on ship. -->
<!-- scope: in-repo -->

**updated_at:** 2026-09-24T18:09:20Z
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
| `bl-0003` | High | bl-0002 | **Caller-input errors reported as backend outages** — add a caller-safe input-error class; preflight position/file in `_position_request`; rope history/stack/transaction misuse raises it, not `RopeError`. Regression of e93207e. [type: bug] [source: mcp-surface-audit-20260923] | M | items/bl-0003.md |

## Medium

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `bl-0009` | Medium | bl-0001 | **Dead-code sweeps exceed 30 s on a 137-file repo** — batch or bound-concurrently run the per-symbol reference lookups in `dead_code_detection` and `unused_symbol_sweep`; target < 10 s on this repo. [type: perf] [source: mcp-surface-audit-20260923] | M | items/bl-0009.md |
| `bl-0023` | Medium | — | **`apply_code_action` promises to list actions but applies the first** — make omitting `action_title` return the available titles (or fix the description) and add a unit test. [type: bug] [source: backlog-remediate-20260924T131340Z] | M | items/bl-0023.md |
| `bl-0025` | Medium | — | **Unhandled-method replies still read as empty results** — route the 5 remaining unhandled-method `return []` branches through `LspFeatureUnsupportedError` (bl-0005's pattern). [type: bug] [source: backlog-remediate-20260924T131340Z] | S | items/bl-0025.md |
| `bl-0026` | Medium | — | **`output_dir`-style params bypass workspace validation** — add directory parameters to `PATH_PARAMS` (or a `DIR_PARAMS` list) so every folder argument is workspace-bounded. [type: security] [source: backlog-remediate-20260924T131340Z] | S | items/bl-0026.md |
| `bl-0028` | Medium | — | **Duplicated import-resolution helpers disagree on `__init__`** — share one helper for import roots and relative-import resolution between `architecture.py` and `dependencies.py`. [type: refactor] [source: backlog-remediate-20260924T131340Z] | M | items/bl-0028.md |
| `bl-0030` | Medium | — | **Investigate Pyright timeouts in the integration suite** — reproduce the load-dependent `TimeoutError` failures and make the suite deterministic (timeout budget, warm-up, or serialization). [type: chore] [source: backlog-remediate-20260924T131340Z] | S | items/bl-0030.md |

## Low

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `bl-0018` | Low | bl-0003 | **Numeric bounds inconsistent across tools** — apply one validation rule for `limit`/`offset`/`depth`/`max_items`/`count` (≥1 or ≥0) uniformly, and reject `undo`/`redo` `count < 1`. [type: bug] [source: mcp-surface-audit-20260923] | M | items/bl-0018.md |
| `bl-0019` | Low | — | **Whole-file rewriters marked non-destructive** — move `format_code`, `apply_lint_fixes`, the import rewriters, `apply_code_action` and `apply_type_annotations` to `DESTRUCTIVE_ANNOTATIONS`. [type: bug] [source: mcp-surface-audit-20260923] | S | items/bl-0019.md |
| `bl-0020` | Low | — | **Tool parameters carry no schema descriptions** — add `Annotated[..., Field(description=...)]` to every parameterized tool in `tool_registry.py`/`server.py`; contract test asserts each advertises ≥1 described parameter. [type: docs] [source: bl-0017] | M | items/bl-0020.md |
| `bl-0021` | Low | bl-0020 | **Closed-set tool params expose no enum or bounds** — type `direction`/`style`/`kind`/`severity_filter`/`source`/`language`/`SignatureOperation.op` as `Literal`, add `ge=0` to line/character positions; contract test checks the schema. [type: bug] [source: bl-0017] | M | items/bl-0021.md |
| `bl-0022` | Low | bl-0021 | **Tools silently accept unknown argument keys** — BLOCKED: operator contract-care decision (Directive #4, PUBLIC repo) first; then emit `additionalProperties: false` and a typed `refactor_transaction` step model. [type: bug] [source: bl-0017] | M | items/bl-0022.md |
| `bl-0024` | Low | — | **AutoImport invalid-statement errors escape redaction** — raise `RopeError` (not `ValueError`) for unusable rope AutoImport output in `imports.py`. [type: bug] [source: backlog-remediate-20260924T131340Z] | S | items/bl-0024.md |
| `bl-0027` | Low | — | **`new_order` negatives are silently dropped** — constrain `SignatureOperation.new_order` items to `>= 0` so a bad reorder is rejected, not ignored. [type: bug] [source: backlog-remediate-20260924T131340Z] | S | items/bl-0027.md |
| `bl-0029` | Low | — | **`create_type_stubs` timeout path has no test** — add a unit test where the createstub subprocess hangs past a patched timeout and assert kill + `PyrightError`. [type: test] [source: backlog-remediate-20260924T131340Z] | S | items/bl-0029.md |
| `bl-0031` | Low | — | **`.worktrees/` shows as untracked** — add `.worktrees/` to `.gitignore` so worktree-based workflows keep the primary checkout clean. [type: chore] [source: backlog-remediate-20260924T131340Z] | S | items/bl-0031.md |
| `bl-0032` | Low | — | **AGENTS.md misstates repo visibility** — state that Jedi-Py-MCP is PUBLIC and record the 2026-09-24 contract ruling (breaking fixes allowed with a `changed-breaking-*` fragment). [type: docs] [source: backlog-remediate-20260924T131340Z] | S | items/bl-0032.md |
| `bl-0033` | Low | — | **`prepare_rename` range math ignores UTF-16** — convert LSP `character` offsets to code points in the `{defaultBehavior}` and placeholder paths. [type: bug] [source: backlog-remediate-20260924T131340Z] | S | items/bl-0033.md |

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
