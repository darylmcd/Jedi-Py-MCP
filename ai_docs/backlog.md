# Backlog

<!-- purpose: Open work only. Slim-index format — triage in the table, implementation detail in items/<id>.md. Sync rows on ship. -->
<!-- scope: in-repo -->

**updated_at:** 2026-09-24T13:19:31Z
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
| `bl-0002` | High | — | **Opaque tool errors drop the reason** — map caller-safe exceptions (ValueError/FileNotFoundError/new input-error class) to `ToolError` with the message in `tool_error_boundary`; `apply_code_action` with no actions returns `[]`. [type: bug] [source: mcp-surface-audit-20260923] | M | items/bl-0002.md |
| `bl-0003` | High | bl-0002 | **Caller-input errors reported as backend outages** — add a caller-safe input-error class; preflight position/file in `_position_request`; rope history/stack/transaction misuse raises it, not `RopeError`. Regression of e93207e. [type: bug] [source: mcp-surface-audit-20260923] | M | items/bl-0003.md |
| `bl-0004` | High | — | **`prepare_rename` always returns null** — accept Pyright's bare-`Range` reply (and `{range, placeholder}`; derive the range only for `{defaultBehavior}`); tighten the integration test to assert a range. [type: bug] [source: mcp-surface-audit-20260923] | S | items/bl-0004.md |
| `bl-0005` | High | — | **selection_range / inlay hints / semantic tokens silently empty** — record Pyright `initialize` capabilities; return an explicit unsupported-by-backend error (or an AST fallback) not `[]`; stop `apply_type_annotations` depending on inlay hints. [type: bug] [source: mcp-surface-audit-20260923] | M | items/bl-0005.md |
| `bl-0006` | High | — | **`generate_code` fails for every kind** — switch to rope `create_generate(kind, …)` (module/package via their real signatures), drop the masking `pyright: ignore`, add an unmocked rope test per kind. [type: bug] [source: mcp-surface-audit-20260923] | S | items/bl-0006.md |
| `bl-0007` | High | — | **`create_type_stubs` reports success without output** — send Pyright's real `createtypestub` argument shape, verify stub files exist, return the created paths and error when none; define `output_dir` semantics. [type: bug] [source: mcp-surface-audit-20260923] | M | items/bl-0007.md |

## Medium

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `bl-0001` | Medium | — | **`dead_code_detection` reports every once-referenced symbol as dead** — references are fetched with `include_declaration=False` but the `same_file_count > 1` threshold assumes the declaration was counted; 306 false positives on this repo's `src/`. [type: bug] [source: refactor-audit-smoke-20260902] | S | items/bl-0001.md |
| `bl-0008` | Medium | — | **Failure IDs are untraceable** — install a stderr log formatter that renders the `extra` fields (exception types, traceback locations) of `tool_backend_failure` events, keyed by Failure ID. [type: reliability] [source: mcp-surface-audit-20260923] | S | items/bl-0008.md |
| `bl-0009` | Medium | bl-0001 | **Dead-code sweeps exceed 30 s on a 137-file repo** — batch or bound-concurrently run the per-symbol reference lookups in `dead_code_detection` and `unused_symbol_sweep`; target < 10 s on this repo. [type: perf] [source: mcp-surface-audit-20260923] | M | items/bl-0009.md |
| `bl-0010` | Medium | — | **Unbounded tool payloads (7.5 MB outline)** — make `get_symbol_outline`'s default cap count all nodes; add default limits + `truncated` to module dependencies, code metrics, dead code and symbol search. [type: perf] [source: mcp-surface-audit-20260923] | M | items/bl-0010.md |
| `bl-0011` | Medium | — | **`check_layer_violations` false-clean on dotted patterns** — prefix-match dotted module patterns, check every `import` alias, resolve relative imports, and warn when a declared layer matches no file. [type: bug] [source: mcp-surface-audit-20260923] | S | items/bl-0011.md |
| `bl-0012` | Medium | — | **`argument_default_inliner` keeps the default** — remove the default from the signature as the tool promises (rope `ArgumentDefaultInliner` removal) and reject a negative `index`. [type: bug] [source: mcp-surface-audit-20260923] | M | items/bl-0012.md |
| `bl-0013` | Medium | — | **Preview hides file moves and creations** — add file-operation entries to `RefactorResult` built from rope move/create changes so `move_module` and `module_to_package` previews show them. [type: bug] [source: mcp-surface-audit-20260923] | M | items/bl-0013.md |
| `bl-0014` | Medium | — | **Nonexistent scope reads as clean** — report a `scan_failure` for a missing `root_path`/`file_path` in dead-code/unused sweeps and outline; stop type coverage reporting 100% for a missing file. [type: bug] [source: mcp-surface-audit-20260923] | M | items/bl-0014.md |
| `bl-0015` | Medium | — | **`manifest.json` invalid for MCPB v0.3** — restructure `author`/`repository`/`server`/`tools`, declare the Python runtime and env vars, drop `categories`; add a manifest schema check to `just ci`. [type: bug] [source: mcp-surface-audit-20260923] | M | items/bl-0015.md |
| `bl-0016` | Medium | — | **LLM copy cites tools absent from the active profile** — make server instructions and `Related:` hints profile-aware; state "acts immediately, no preview" on undo/redo/commit/transaction/stubs/restart. [type: docs] [source: mcp-surface-audit-20260923] | M | items/bl-0016.md |

## Low

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `bl-0018` | Low | bl-0003 | **Numeric bounds inconsistent across tools** — apply one validation rule for `limit`/`offset`/`depth`/`max_items`/`count` (≥1 or ≥0) uniformly, and reject `undo`/`redo` `count < 1`. [type: bug] [source: mcp-surface-audit-20260923] | M | items/bl-0018.md |
| `bl-0019` | Low | — | **Whole-file rewriters marked non-destructive** — move `format_code`, `apply_lint_fixes`, the import rewriters, `apply_code_action` and `apply_type_annotations` to `DESTRUCTIVE_ANNOTATIONS`. [type: bug] [source: mcp-surface-audit-20260923] | S | items/bl-0019.md |
| `bl-0020` | Low | — | **Tool parameters carry no schema descriptions** — add `Annotated[..., Field(description=...)]` to every parameterized tool in `tool_registry.py`/`server.py`; contract test asserts each advertises ≥1 described parameter. [type: docs] [source: bl-0017] | M | items/bl-0020.md |
| `bl-0021` | Low | bl-0020 | **Closed-set tool params expose no enum or bounds** — type `direction`/`style`/`kind`/`severity_filter`/`source`/`language`/`SignatureOperation.op` as `Literal`, add `ge=0` to line/character positions; contract test checks the schema. [type: bug] [source: bl-0017] | M | items/bl-0021.md |
| `bl-0022` | Low | bl-0021 | **Tools silently accept unknown argument keys** — BLOCKED: operator contract-care decision (Directive #4, PUBLIC repo) first; then emit `additionalProperties: false` and a typed `refactor_transaction` step model. [type: bug] [source: bl-0017] | M | items/bl-0022.md |

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
