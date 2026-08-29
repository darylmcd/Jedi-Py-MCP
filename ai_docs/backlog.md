# Backlog

<!-- purpose: Open work only. Slim-index format — triage in the table, implementation detail in items/<id>.md. Sync rows on ship. -->
<!-- scope: in-repo -->

**updated_at:** 2026-08-29T13:35:19Z
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
| **MUST** | Spill implementation detail (`Anchors:`, acceptance criteria, long-form evidence) to `ai_docs/items/<id>.md` for any **code-touching row**, and point the `detail` cell at it. Use `templates/items.md`. Pure-prose rows (Defer rationale, decision notes) may stay inline with `detail: —`. |
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

## Medium

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|

## Low

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `cand-convert-to-dataclass` | Low | — | **New tool `convert_to_dataclass`** — modernize a plain class to `@dataclass`, field types from Pyright inference, on the CST apply foundation. Weaker evidence — proposed candidate. [type: enhancement] [source: candidate-proposal] | L | items/cand-convert-to-dataclass.md |
| cand-extract-class | Low | — | **New tool `extract_class`** — move a cohesive subset of fields/methods into a new collaborator class via the CST foundation (rope 1.14 has no ExtractClass). Weaker evidence — proposed candidate. [type: enhancement] [source: candidate-proposal] | M | items/cand-extract-class.md |
| cand-convert-function-method | Low | — | **Symmetric tools `convert_function_to_method` / `convert_method_to_function`** — CST transform + caller rewrites via `find_references`. Weaker evidence — proposed candidate. [type: enhancement] [source: candidate-proposal] | M | items/cand-convert-function-method.md |
| cand-split-module | Low | — | **New tool `split_module`** — partition a module into N modules by symbol selection (batch CST emit; rope `Move` for import rewrites v1). Weaker evidence — proposed candidate. [type: enhancement] [source: candidate-proposal] | M | items/cand-split-module.md |
| `cand-docstring-sync` | Low | — | **New tool `docstring_sync`** — diff signatures vs docstring params and auto-update Google/NumPy/Sphinx styles. Weaker evidence — proposed candidate (BRAIN-007). [type: enhancement] [source: application-brainstorm] | L | items/cand-docstring-sync.md |
| cand-rename-cst-alias | Low | — | **LibCST alias-aware `rename_symbol` variant** — rewrite `import X as Y` / `from m import X as Y` rebindings rope/Jedi miss; abort on alias collision; dry-run. [type: enhancement] [source: brainstorm-BRAIN-001] | M | items/cand-rename-cst-alias.md |
| cand-fix-circular-imports | Low | — | **New tool: auto-fix circular imports** — detect cycles via `get_module_dependencies`, hoist type-only edge imports into `if TYPE_CHECKING:` + stringify annotations; conservative, dry-run mandatory. [type: enhancement] [source: brainstorm-BRAIN-004] | M | items/cand-fix-circular-imports.md |
| cand-cross-project-rename-topo | Low | — | **Order `multi_project_rename` by reverse-topo** — build cross-project import graph; apply downstream-before-upstream; abort on inter-project cycle. Correctness fix (today: arbitrary order). [type: defect] [source: brainstorm-BRAIN-009] | M | items/cand-cross-project-rename-topo.md |
| cand-type-stub-freshness | Low | — | **New tool: type-stub freshness audit** — diff `.pyi` stub signatures vs `.py` impl, surface drift; handle `@overload`/`Protocol` without churn; optional `create_type_stubs` regen. [type: enhancement] [source: brainstorm-BRAIN-008] | M | items/cand-type-stub-freshness.md |
| cand-convert-typeddict-pydantic | Low | — | **New tools: convert to TypedDict / Pydantic v2** — dict-shaped returns→TypedDict; typed classes→Pydantic v2; field types from Pyright; preview-default. Remaining BRAIN-003 scope beyond the dataclass slice. [type: enhancement] [source: brainstorm-BRAIN-003] | M | items/cand-convert-typeddict-pydantic.md |

## Defer

<!-- Explicitly parked. Record WHY in the `do` cell. -->

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| cand-find-cyclic-imports | Defer | — | **Dedicated cycle report — parked as redundant** — `get_module_dependencies` already returns cycles; unblock only if per-edge provenance (file:line:col per import) is added as a real delta. [type: enhancement] [source: candidate-proposal] | — | items/cand-find-cyclic-imports.md |

## Refs

- `ai_docs/workflow.md` — execution flow and backlog closure rules
- `ai_docs/architecture.md` — current system architecture
- `ai_docs/items/` — per-row implementation detail (Anchors/Acceptance/Evidence); seed new files from `templates/items.md`
- `ai_docs/references/mcp_best_practices/README.md` — MCP design reference
- `../CI_POLICY.md` — merge gating policy
- `../audit-reports/application-brainstorm.md` — not-yet-sized product/refactor ideas (BRAIN-001..022 as of Pass 6, 2026-06-19) for brainstorm/planning intake; promote a BRAIN row to a sized backlog row when its first slice is ready
- `ai_docs/archive/plans/20260527T205134Z_backlog-sweep/plan.md` — Backlog sweep (20260527T205134Z), completed 2026-05-29, archived 2026-07-08 (30+ days stable). Shipped 6 initiatives across 6 PRs (#50, #51, #52, #57, #58, #59); closed 6 backlog rows.
