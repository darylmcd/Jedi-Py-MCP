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

## Medium

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `nested-workspace-recursive-scan` | Medium | — | **Keep recursive scans inside the selected workspace** — Prune nested workspace boundaries from implicit file enumeration used by workspace tools. [type: bug] [source: remediate-20261113] | M | items/nested-workspace-recursive-scan.md |
| `multi-project-rename-roots` | Medium | — | **BLOCKED: operator decision** (which roots may be named: registered only, or an allowlist?). Authorize multi_project_rename additional_roots, then enforce before opening any Project. [type: bug] [source: remediate-20261117] | M | items/multi-project-rename-roots.md |
| `workspace-selection-authorized-roots` | Medium | — | **BLOCKED: operator decision** (may a path select an unregistered marker-bearing project?). Restrict path-selected workspaces to authorized roots, then enforce. [type: bug] [source: remediate-20261117] | M | items/workspace-selection-authorized-roots.md |
| `bom-mishandled-edit-paths` | Medium | — | **UTF-8 BOM files are mishandled by edit and write paths** — Round-trip BOM files byte-exactly: line-0 offsets shift by one (the BOM counts as character 0), and ruff format, docstring sync and CST apply drop the BOM. [type: bug] [source: remediate-20261117] | L | items/bom-mishandled-edit-paths.md |
| `rope-timeout-zombie-concurrent-calls` | Medium | — | **A timed-out rope call overlaps the next call** — the abandoned worker (lease held, ADR 0013) keeps running while the next call uses the same non-thread-safe project: serialize per backend. [type: bug] [source: remediate-20261117] | M | items/rope-timeout-zombie-concurrent-calls.md |

## Low

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| `bl-0052` | Low | — | **get_diagnostics file_paths has no per-file failure channel** — file_paths stays sequential fail-fast; add per-file failure reporting (output-contract decision). CancelledError propagation done (#226, #228). [type: bug] [source: backlog-remediate-20260926T234845Z] | S | items/bl-0052.md |
| `bl-0053` | Low | — | **Silent limit/offset guards unreachable after schema bounds** — reject or share the backend `limit > 0` / `offset > 0` branches bl-0018 made MCP-unreachable. [type: refactor] [source: backlog-remediate-20260926T234845Z] | M | items/bl-0053.md |
| `bl-0054` | Low | — | **Two LSP-range converters diverge** — merge `helpers._lsp_range` (fails on missing coords) and `lsp_converters.model_range` (zero-defaults them) into one converter with explicit strictness. [type: refactor] [source: backlog-remediate-20260927T020158Z] | M | items/bl-0054.md |
| `build-unified-diff-direct-caller-containment` | Low | — | **Containment at the diff library seam** — add workspace containment to build_unified_diff/diff_preview, or document the boundary as the only guard. [type: bug] [source: remediate-20261117] | M | items/build-unified-diff-direct-caller-containment.md |
| `error-boundary-swallows-resolution-error` | Low | — | **Stop swallowing WorkspaceResolutionError; derive PATH_PARAMS** — fix _require_single_workspace swallow; derive contract-test PATH_PARAMS from live schemas. [type: refactor] [source: remediate-20261117] | S | items/error-boundary-swallows-resolution-error.md |
| `output-dir-anchorless-boundary` | Low | — | **BLOCKED: operator decision** (must an absolute output_dir lie inside the call workspace?). Tie anchorless output_dir to its workspace, then enforce. [type: bug] [source: remediate-20261117] | M | items/output-dir-anchorless-boundary.md |
| `lsp-respond-configuration-null` | Low | — | **LSP _respond answers workspace/configuration with null** — util/lsp_client.py _respond answers every server request with null; answer per method (configuration -> list sized to params.items; others null). [type: bug] [source: remediate-20261117] | S | items/lsp-respond-configuration-null.md |
| `search-open-target-files-restart` | Low | — | **open_target_files loses its open set on Pyright restart** — make the multi-file open set restart-safe and give ensure_file_open explicit semantics (it only dedups, never re-syncs edited content). [type: bug] [source: remediate-20261117] | M | items/search-open-target-files-restart.md |
| `pure-file-tools-start-backends` | Low | — | **Pure file/AST tools start language backends** — about 20 tools do _ = get_current_backends() for AST-only work; give them the root-only workspace mode (follows diff-preview-root-only scaffold). [type: debt] [source: remediate-20261117] | M | items/pure-file-tools-start-backends.md |
| `real-registry-ctx-test-helper-spies` | Low | — | **_real_registry_ctx spies get_backends** — the test helper never runs real registry initialization, so 'real registry' tests overclaim: add a real-init seam or rename/limit the claims. [type: debt] [source: remediate-20261117] | S | items/real-registry-ctx-test-helper-spies.md |
| `rope-signature-override-and-kwonly-gaps` | Low | — | **Rope signature gaps: kw-only/pos-only refusal; overrides need operator call** — refuse ops on targets with `*`, kw-only or `/` params (typed error before DefinitionInfo.read); overrides decision pending, see item note. [type: bug] [source: remediate-20261117] | M | items/rope-signature-override-and-kwonly-gaps.md |
| `identifier-validators-unify` | Low | — | **Unify remaining identifier validators** — util.shared.validate_identifier is the one NFKC-aware validator; rope_backend and class_extraction still carry inline identifier checks with different messages: route them through it. [type: debt] [source: remediate-20261117] | M | items/identifier-validators-unify.md |
| `implicit-workspace-unlocked-window` | Low | — | **BLOCKED: operator decision** on selecting a workspace before parameter validation (coupled to workspace-selection-authorized-roots). #211 closed the shutdown_all window. [type: debt] [source: remediate-20261117] | S | items/implicit-workspace-unlocked-window.md |
| `test-error-boundary-split` | Low | — | **Split test_error_boundary.py by concern** — tests/unit/test_error_boundary.py is about 1300 lines mixing path scoping, workspace resolution and registry-backed cases over heavy MagicMock registries: split by boundary concern with shared fixtures. [type: debt] [source: remediate-20261117] | S | items/test-error-boundary-split.md |
| `test-map-name-column-derivation` | Low | — | **test_map derives name columns by substring** — get_test_coverage_map takes ast.walk order and re-derives columns with source_lines[line].find(name), which can hit a substring in a decorator or another identifier: use the AST column offsets. [type: bug] [source: remediate-20261117] | S | items/test-map-name-column-derivation.md |
| `file-filter-helper-cleanup` | Low | — | **file_filter helper cleanup** — drop the one-line python_files pass-through and its unused exclude_dirs; resolve the root once per sweep instead of per file in is_test_file. [type: debt] [source: remediate-20261117] | M | items/file-filter-helper-cleanup.md |
| `registry-known-roots-not-pruned` | Low | — | **Prune evicted auto roots** — Evicted auto roots stay in known roots; see the item file. [type: bug] [source: remediate-20261117] | S | items/registry-known-roots-not-pruned.md |
| `registry-shutdown-sequential` | Low | — | **Isolate per-backend shutdown failures** — One BaseException skips the remaining shutdowns; see the item file. [type: bug] [source: remediate-20261117] | S | items/registry-shutdown-sequential.md |
| `active-tool-profile-import-time` | Low | — | **Discover the tool profile at build time** — Tool profile read at import time; see the item file. [type: debt] [source: remediate-20261117] | S | items/active-tool-profile-import-time.md |
| `worktree-editable-install-shadows-src` | Low | — | **Make worktree test runs import their own src** — Worktree pytest runs test the primary checkout; see the item file. [type: debt] [source: remediate-20261117] | S | items/worktree-editable-install-shadows-src.md |
| `stale-server-py-doc-pointers` | Low | — | **Repoint docs naming server.py as the registration layer** — Stale registration-layer pointers; see the item file. [type: debt] [source: remediate-20261117] | S | items/stale-server-py-doc-pointers.md |
| `test-mcp-protocol-server-rebuild` | Low | — | **Share built servers in contract tests** — Server rebuilt per contract test; see the item file. [type: debt] [source: remediate-20261117] | S | items/test-mcp-protocol-server-rebuild.md |
| `introduce-inline-parameter-kwonly` | Low | — | **introduce_parameter/inline_parameter break keyword-only targets** — Refuse keyword-only targets with a typed ToolInputError, or emit parseable output, in rope introduce_parameter and inline_parameter, which currently drop the bare star. [type: bug] [source: remediate-20261117] | S | items/introduce-inline-parameter-kwonly.md |
| `registry-tests-unmatched-release` | Low | — | **Registry tests acquire leases they never release** — Pair every get_backends in test_workspace_registry.py with a release (fixture or try/finally) so tests model finished requests; about 19 acquires versus 2 releases today. [type: debt] [source: remediate-20261117] | S | items/registry-tests-unmatched-release.md |
| `python-detect-venvpath-unc` | Low | — | **python_detect probes UNC venvPath and VIRTUAL_ENV values** — Skip or reject UNC and device values from the pyproject poetry venv path and VIRTUAL_ENV before is_dir/exists in python_detect, using is_network_or_device_path. [type: bug] [source: remediate-20261117] | M | items/python-detect-venvpath-unc.md |
| `ruff-format-drift` | Low | — | **ruff format flags 81 files repo-wide; CI gates only 5** — Decide: run ruff format over the tree and gate it in the justfile, or document why only the converter files are gated; today 81 files would be reformatted. [type: debt] [source: remediate-20261117] | M | items/ruff-format-drift.md |
| `newline-handling-duplicates` | Low | — | **Newline normalisation copied across writers** — reuse one public helper (diff._normalize_newlines) in cst_apply and docstrings; make format and lint_fix write via write_atomic_if_unchanged like the other writers. [type: debt] [source: remediate-20261117] | L | items/newline-handling-duplicates.md |
| `non-nfkc-workspace-breaks-rope` | Low | — | **One non-NFKC identifier makes every rope tool fail** — Scope the rope MismatchedTokenError from a non-NFKC workspace file to operations that need it, or have every rope tool name the offending file, not only change_signature. [type: bug] [source: remediate-20261117] | M | items/non-nfkc-workspace-breaks-rope.md |
| `signature-error-suffix-wording` | Low | — | **Non-NFKC error ends with a misleading parameter suffix** — Drop or replace the trailing parameter: line suffix on the non-NFKC ToolInputError, since the cause is workspace-wide and no single parameter is at fault. [type: debt] [source: remediate-20261117] | S | items/signature-error-suffix-wording.md |
| `path-resolve-triple-copy` | Low | — | **directory resolve-or-default logic copied three times** — Extract one helper for resolving an optional directory against the workspace root and use it in diagnostics, search and outline; outline also adds an is_dir check. [type: debt] [source: remediate-20261117] | M | items/path-resolve-triple-copy.md |
| `shutdown-all-closes-rope-under-worker` | Low | — | **shutdown_all closes rope under a running worker** — _release_resources calls rope.close() while a leased worker may still use the project (ADR 0013 keeps shutdown non-waiting): add a bounded drain or a worker-safe close. [type: bug] [source: remediate-20261117] | M | items/shutdown-all-closes-rope-under-worker.md |
| `structural-search-abandoned-scan-threads` | Low | — | **structural_search fans out unbounded to_thread scans** — structural.py gathers one asyncio.to_thread per candidate file with no concurrency bound and abandons them on cancel; bound the fan-out and make cancellation stop queued work. [type: bug] [source: remediate-20261117] | S | items/structural-search-abandoned-scan-threads.md |
| `type-stubs-abandoned-move` | Low | — | **create_type_stubs can abandon a shutil.move mid-mutation** — type_stubs.py runs shutil.move in asyncio.to_thread; a cancel abandons the thread mid-move; shield it or run it to completion. [type: bug] [source: remediate-20261117] | S | items/type-stubs-abandoned-move.md |
| `abandoned-worker-delays-process-exit` | Low | — | **Abandoned worker threads can delay process exit** — asyncio.run's executor shutdown joins a stuck rope worker: bound it or use a daemon-thread strategy. [type: bug] [source: remediate-20261117] | M | items/abandoned-worker-delays-process-exit.md |
| `pyright-document-request-open-peer-sync` | Low | — | **Hover/references do not resync other open documents** — only diagnostics do (PR #226); _document_request refreshes just its own file: resync peers without O(N^2) stats. [type: bug] [source: remediate-20261117] | M | items/pyright-document-request-open-peer-sync.md |
| `pyright-start-double-start-guard` | Low | — | **PyrightLSPClient.start twice replaces the client unshut** — Calling start() twice replaces _client without stopping the first process; decide the policy (raise, idempotent, or restart) and enforce it. [type: bug] [source: remediate-20261117] | S | items/pyright-start-double-start-guard.md |
| `workspace-backends-shutdown-during-initialize` | Low | — | **WorkspaceBackends.shutdown is a no-op while initialize runs** — shutdown returns early when not _initialized, so a shutdown racing an in-flight initialize does nothing and the backends can start after it; reproduce and fix or prove unreachable. [type: bug] [source: remediate-20261117] | S | items/workspace-backends-shutdown-during-initialize.md |
| `pyright-publish-diagnostics-capability-stale` | Low | — | **Client still declares the publishDiagnostics capability** — Pushes are ignored since PR #228 but the initialize params still declare textDocument.publishDiagnostics with versionSupport; drop it if Pyright still pulls correctly. [type: debt] [source: remediate-20261117] | S | items/pyright-publish-diagnostics-capability-stale.md |
| `python-files-blocking-walk` | Low | — | **python_files walks the tree synchronously on the event loop** — every workspace scan blocks the loop in os.walk: move it to a worker thread or cache it. [type: debt] [source: remediate-20261117] | M | items/python-files-blocking-walk.md |
| `scan-open-documents-left-open` | Low | — | **Tolerant scans leave the documents they opened open** — get_workspace_diagnostics and dead_code_detection use close_opened=False, so every scan grows the Pyright open set until restart; reuse the PR #228 scan ownership to close what they opened. [type: bug] [source: remediate-20261117] | M | items/scan-open-documents-left-open.md |
| `pull-many-swallows-programming-errors` | Low | — | **_pull_many records programming errors as scan failures** — per-file except Exception hides TypeError/AttributeError: catch only the backend error family. [type: bug] [source: remediate-20261117] | S | items/pull-many-swallows-programming-errors.md |

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
