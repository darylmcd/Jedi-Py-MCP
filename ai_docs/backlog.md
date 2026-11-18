# Backlog

<!-- purpose: Open work only. Slim-index format — triage in the table, implementation detail in items/<id>.md. Sync rows on ship. -->
<!-- scope: in-repo -->

<!-- 2026-06-19: shipped cand-server-status, cand-security-autofix, changelog-tool-count-drift, cand-structural-replace (+RCE fix), change_signature annotation restore. -->
<!-- 2026-07-08: doc-audit filed 2 new rows (backend-fallback-swallowed-exceptions, dead-code-symbol-scan-silent-drop); Refs updated for the 20260527T205134Z plan archival. -->


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
| `bl-0056` | High | diff-preview-root-only | **Path-less tools must not pick a workspace silently** — add root_path to the 26 path-less tools and raise coded AMBIGUOUS_WORKSPACE instead of most-recent/pre-warm fallback; ADR 0007, breaking. [type: bug] [source: retro-20260927] | L | items/bl-0056.md |
| `rope-signature-rename-bindings` | High | — | **Preserve signature rename bindings** — Rename parameter references and preserve positional and keyword argument values at call sites. [type: bug] [source: remediate-20261113] | M | items/rope-signature-rename-bindings.md |
| `diff-preview-root-only` | High | — | **diff_preview must not resolve backends** — dispatch diff_preview with a root-only workspace mode: no backend start, works with zero or several live workspaces; empty edits succeed. [type: bug] [source: remediate-20261117] | M | items/diff-preview-root-only.md |

## Medium

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `nested-workspace-recursive-scan` | Medium | — | **Keep recursive scans inside the selected workspace** — Prune nested workspace boundaries from implicit file enumeration used by workspace tools. [type: bug] [source: remediate-20261113] | M | items/nested-workspace-recursive-scan.md |
| `pyright-workspace-diagnostic-snapshot` | Medium | — | **Analyze pathless diagnostics across the workspace** — Collect current diagnostics for the documented workspace scope and surface analysis failures. [type: bug] [source: remediate-20261113] | M | items/pyright-workspace-diagnostic-snapshot.md |
| `pyright-diagnostics-import-freshness` | Medium | — | **Refresh changed imports before diagnostic analysis** — Synchronize edited open dependencies before analyzing their importers. [type: bug] [source: remediate-20261113] | M | items/pyright-diagnostics-import-freshness.md |
| `workspace-eviction-active-requests` | Medium | — | **Keep active workspace backends alive through dispatch** — Coordinate registry eviction with in-flight requests and prohibit respawning an evicted transport. [type: bug] [source: remediate-20261113] | M | items/workspace-eviction-active-requests.md |
| `multi-project-rename-roots` | Medium | — | **Authorize multi_project_rename additional_roots** — Operator decision needed first: which roots may be named (registered only? allowlist?), then enforce before opening any Project. [type: bug] [source: remediate-20261117] | M | items/multi-project-rename-roots.md |
| `workspace-selection-authorized-roots` | Medium | — | **Restrict path-selected workspaces to authorized roots** — Operator decision needed first: may a path select an unregistered marker-bearing project? Then enforce. [type: bug] [source: remediate-20261117] | M | items/workspace-selection-authorized-roots.md |
| `signature-add-reorder-default-order-validation` | Medium | — | **Validate parameter order for add/reorder** — reject add/reorder leaving a required parameter after a defaulted one in the simulated walk. [type: bug] [source: remediate-20261117] | S | items/signature-add-reorder-default-order-validation.md |

## Low

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `bl-0051` | Low | — | **Test-file exclusion ignores tests/ trees** — `is_test_file` matches filenames only, so fixture modules under `tests/` become sweep targets with `exclude_test_files=True`. [type: bug] [source: backlog-remediate-20260926T234845Z] | S | items/bl-0051.md |
| `bl-0052` | Low | — | **get_diagnostics batch has no per-file failure channel** — Return per-file diagnostic failures and propagate workspace scan cancellation. [type: bug] [source: backlog-remediate-20260926T234845Z] | S | items/bl-0052.md |
| `bl-0053` | Low | — | **Silent limit/offset guards unreachable after schema bounds** — reject or share the backend `limit > 0` / `offset > 0` branches bl-0018 made MCP-unreachable. [type: refactor] [source: backlog-remediate-20260926T234845Z] | M | items/bl-0053.md |
| `bl-0054` | Low | — | **Two LSP-range converters diverge** — merge `helpers._lsp_range` (fails on missing coords) and `lsp_converters.model_range` (zero-defaults them) into one converter with explicit strictness. [type: refactor] [source: backlog-remediate-20260927T020158Z] | M | items/bl-0054.md |
| `backend-threading-input-error-doc` | Low | — | **Document worker input error propagation** — Describe how the shared thread wrapper preserves ToolInputError. [type: bug] [source: remediate-20261113] | S | items/backend-threading-input-error-doc.md |
| `windows-unc-path-preflight-io` | Low | — | **Reject UNC/device paths before filesystem access** — reject (or confirm and document) UNC/device-namespace paths before resolve()/marker probes in the workspace boundary. [type: bug] [source: remediate-20261117] | M | items/windows-unc-path-preflight-io.md |
| `registry-resolve-root-mutates-unlocked` | Low | — | **Make resolve_workspace_root pure** — stop mutating _known_roots/_auto_roots on read; register on dispatch under the lock. [type: bug] [source: remediate-20261117] | M | items/registry-resolve-root-mutates-unlocked.md |
| `registry-set-roots-cancel-safety` | Low | — | **Cancel-safe set_roots and _run_to_completion** — reorder set_roots state replacement; retrieve shielded task exceptions on cancel; add tests. [type: bug] [source: remediate-20261117] | S | items/registry-set-roots-cancel-safety.md |
| `server-startup-teardown-guard` | Low | — | **Guard lifespan startup with teardown** — move set_roots and eager get_backends inside the try/finally owning shutdown_all. [type: bug] [source: remediate-20261117] | S | items/server-startup-teardown-guard.md |
| `build-unified-diff-direct-caller-containment` | Low | — | **Containment at the diff library seam** — add workspace containment to build_unified_diff/diff_preview, or document the boundary as the only guard. [type: bug] [source: remediate-20261117] | M | items/build-unified-diff-direct-caller-containment.md |
| `error-boundary-swallows-resolution-error` | Low | — | **Stop swallowing WorkspaceResolutionError; derive PATH_PARAMS** — fix _require_single_workspace swallow; derive contract-test PATH_PARAMS from live schemas. [type: refactor] [source: remediate-20261117] | S | items/error-boundary-swallows-resolution-error.md |
| `output-dir-anchorless-boundary` | Low | — | **Tie anchorless output_dir to its workspace** — Operator decision needed first: must absolute output_dir be inside the call's workspace? Then enforce. [type: bug] [source: remediate-20261117] | M | items/output-dir-anchorless-boundary.md |
| `lsp-respond-configuration-null` | Low | — | **LSP _respond answers workspace/configuration with null** — util/lsp_client.py _respond answers every server request with null; answer per method (configuration -> list sized to params.items; others null). [type: bug] [source: remediate-20261117] | S | items/lsp-respond-configuration-null.md |
| `search-open-target-files-restart` | Low | — | **open_target_files loses its open set on Pyright restart** — make the multi-file open set restart-safe and give ensure_file_open explicit semantics (it only dedups, never re-syncs edited content). [type: bug] [source: remediate-20261117] | M | items/search-open-target-files-restart.md |
| `pure-file-tools-start-backends` | Low | bl-0056 | **Pure file/AST tools start language backends** — about 20 tools do _ = get_current_backends() for AST-only work; give them the root-only workspace mode (follows diff-preview-root-only scaffold). [type: debt] [source: remediate-20261117] | M | items/pure-file-tools-start-backends.md |
| `server-module-global-workspace-root` | Low | — | **server.py module-global _workspace_root** — run_server mutates a module global (noqa PLW0603) read by the lifespan; thread the root through the lifespan/registry instead. [type: debt] [source: remediate-20261117] | S | items/server-module-global-workspace-root.md |
| `tool-records-split-server-registry` | Low | — | **Tool records split across server.py and tool_registry.py** — delegates live in both (EXPLICIT_TOOL_RECORDS vs TOOL_RECORDS); consolidate into one table with an identical tool surface. [type: debt] [source: remediate-20261117] | M | items/tool-records-split-server-registry.md |
| `real-registry-ctx-test-helper-spies` | Low | — | **_real_registry_ctx spies get_backends** — the test helper never runs real registry initialization, so 'real registry' tests overclaim: add a real-init seam or rename/limit the claims. [type: debt] [source: remediate-20261117] | S | items/real-registry-ctx-test-helper-spies.md |

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
