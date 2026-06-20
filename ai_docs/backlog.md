# Backlog

<!-- purpose: Open work only. Slim-index format — triage in the table, implementation detail in items/<id>.md. Sync rows on ship. -->
<!-- scope: in-repo -->

**updated_at:** 2026-06-20T04:21:58Z
<!-- 2026-06-19: shipped cand-server-status, cand-security-autofix, changelog-tool-count-drift, cand-structural-replace (+RCE fix), change_signature annotation restore. -->

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
- Best-practices reference: `ai_docs/references/mcp_best_practices.md`.
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
| mypy-2x-migration | Medium | — | **Migrate to mypy 2.x** — bump `mypy>=2.0` and fix the 344 strict-mode errors at source (typed `MCPContext` alias, typed `@mcp.tool` wrappers, Optional-narrowing); no `# type: ignore` band-aids. Effective-L / design-gated (decorator-typing strategy) — route via `/backlog-sweep:prepare`, not top-n. [type: upgrade] [source: upgrade-eligibility-20260527] | M | items/mypy-2x-migration.md |
| rollback-change-stack-noop | Medium | — | **`rollback_change_stack` does not revert pushed changes** — it nulls `_change_stack` without `pop_all()`/undo, so a non-empty stack's edits stay applied on disk; add a real rollback + verify `commit_change_stack` semantics. [type: defect] [source: pr70-cq-review-20260620] | S | items/rollback-change-stack-noop.md |
| refactor-transaction-overlap-line-align | Medium | — | **`refactor_transaction` overlap detection over-aborts** — `_changed_char_spans` aligns lines by index, so a whole-line insert/delete falsely marks shifted lines as overlapping; line-align before char-diffing. [type: defect] [source: pr70-cq-review-20260620] | S | items/refactor-transaction-overlap-line-align.md |
| position-convention-positions-list-tools | Medium | — | **Extend 0-based convention to Position-wrapped tools** — `selection_range`/`test_impact_select` take `positions: list[Position]`; add the phrase to their descriptions and widen the `test_server.py` selector to the positions-list schema. [type: docs] [source: pr72-cq-review-20260620] | M | items/position-convention-positions-list-tools.md |

## Low

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| known-rope-annotations | Low | — | **`change_signature` strips defaults** — type annotations are now restored via the CST post-pass (`signature_annotations.py`, shipped); rope still drops default values on rename/normalize. Residual tracked by `cand-change-signature-cst`. [type: known-limitation] [source: inline-callsite-doc] | M | items/known-rope-annotations.md |
| cand-change-signature-cst | Low | — | **`change_signature` defaults + combined-op edge** — annotation restore shipped (CST post-pass); remaining: preserve default values rope drops, and restore the renamed-param annotation under combined reorder+rename. [type: defect] [source: brainstorm-BRAIN-015] | M | items/cand-change-signature-cst.md |
| cand-convert-to-dataclass | Low | — | **New tool `convert_to_dataclass`** — modernize a plain class to `@dataclass`, field types from Pyright inference, on the CST apply foundation. Weaker evidence — proposed candidate. [type: enhancement] [source: candidate-proposal] | M | items/cand-convert-to-dataclass.md |
| cand-extract-class | Low | — | **New tool `extract_class`** — move a cohesive subset of fields/methods into a new collaborator class via the CST foundation (rope 1.14 has no ExtractClass). Weaker evidence — proposed candidate. [type: enhancement] [source: candidate-proposal] | M | items/cand-extract-class.md |
| cand-convert-function-method | Low | — | **Symmetric tools `convert_function_to_method` / `convert_method_to_function`** — CST transform + caller rewrites via `find_references`. Weaker evidence — proposed candidate. [type: enhancement] [source: candidate-proposal] | M | items/cand-convert-function-method.md |
| cand-split-module | Low | — | **New tool `split_module`** — partition a module into N modules by symbol selection (batch CST emit; rope `Move` for import rewrites v1). Weaker evidence — proposed candidate. [type: enhancement] [source: candidate-proposal] | M | items/cand-split-module.md |
| cand-docstring-sync | Low | — | **New tool `docstring_sync`** — diff signatures vs docstring params and auto-update Google/NumPy/Sphinx styles. Weaker evidence — proposed candidate (BRAIN-007). [type: enhancement] [source: application-brainstorm] | M | items/cand-docstring-sync.md |
| pyright-position-request-param-merge-guard | Low | — | **Harden `_position_request` envelope merge** — stop `extra_params` from clobbering `textDocument`/`position` (base keys win or `ValueError`); latent only. [type: defect] [source: backlog-sweep-20260528-pr50] | S | items/pyright-position-request-param-merge-guard.md |
| jedi-hierarchy-swallowed-exceptions | Low | — | **Document/narrow 8 best-effort exception swallows** — `jedi_backend.py` (6) + `hierarchy.py` (2): narrow the caught type and/or add boundary-marker comments; no behaviour change. [type: refactor] [source: doc-audit-20260528] | M | items/jedi-hierarchy-swallowed-exceptions.md |
| codemod-multifile-atomicity | Low | — | **Multi-file codemod apply is non-atomic (CST + rope/LSP)** — route both write loops (CST + `result_from_text_edits`) through one shared atomic/partial-result helper. [type: defect] [source: structural-replace-impl-review-20260619] | M | items/codemod-multifile-atomicity.md |
| cand-rename-cst-alias | Low | — | **LibCST alias-aware `rename_symbol` variant** — rewrite `import X as Y` / `from m import X as Y` rebindings rope/Jedi miss; abort on alias collision; dry-run. [type: enhancement] [source: brainstorm-BRAIN-001] | M | items/cand-rename-cst-alias.md |
| cand-fix-circular-imports | Low | — | **New tool: auto-fix circular imports** — detect cycles via `get_module_dependencies`, hoist type-only edge imports into `if TYPE_CHECKING:` + stringify annotations; conservative, dry-run mandatory. [type: enhancement] [source: brainstorm-BRAIN-004] | M | items/cand-fix-circular-imports.md |
| cand-cross-project-rename-topo | Low | — | **Order `multi_project_rename` by reverse-topo** — build cross-project import graph; apply downstream-before-upstream; abort on inter-project cycle. Correctness fix (today: arbitrary order). [type: defect] [source: brainstorm-BRAIN-009] | M | items/cand-cross-project-rename-topo.md |
| cand-type-stub-freshness | Low | — | **New tool: type-stub freshness audit** — diff `.pyi` stub signatures vs `.py` impl, surface drift; handle `@overload`/`Protocol` without churn; optional `create_type_stubs` regen. [type: enhancement] [source: brainstorm-BRAIN-008] | M | items/cand-type-stub-freshness.md |
| cand-convert-typeddict-pydantic | Low | — | **New tools: convert to TypedDict / Pydantic v2** — dict-shaped returns→TypedDict; typed classes→Pydantic v2; field types from Pyright; preview-default. Remaining BRAIN-003 scope beyond the dataclass slice. [type: enhancement] [source: brainstorm-BRAIN-003] | M | items/cand-convert-typeddict-pydantic.md |
| changelog-unreleased-tool-tally | Low | — | **Fix CHANGELOG [Unreleased] stale tool tally** — bump the reconciliation line from 96 to 97 to match the [Unreleased] Added entries and the live surface. [type: docs] [source: discovery-sweep-20260619] | S | items/changelog-unreleased-tool-tally.md |
| structural-search-silent-file-drop | Low | — | **Surface skipped files in structural_search** — per-file read/parse failures are dropped by `gather(return_exceptions=True)` with no signal; report a skipped count or note. [type: observability] [source: discovery-sweep-20260619] | S | items/structural-search-silent-file-drop.md |
| cand-structured-error-envelope | Low | — | **Structured error envelope at the MCP boundary** — map each `BackendError` subclass to a stable code in `_tool_error_boundary` instead of bare `ValueError`; message text unchanged. [type: enhancement] [source: BRAIN-018 · audit-reports/application-brainstorm.md] | M | items/cand-structured-error-envelope.md |
| cand-test-impact-nodeid-precision | Low | — | **Precise pytest node-IDs for test_impact_select** — emit `file::Class::method` for class-based test callers (reuse hierarchy.py class derivation); parametrized cases stay slice 2. [type: enhancement] [source: BRAIN-021 · audit-reports/application-brainstorm.md] | S | items/cand-test-impact-nodeid-precision.md |
| refactor-transaction-path-format-unify | Low | — | **Unify `refactor_transaction` result path formatting** — `files_affected` (backend `_absolute_path`) vs `diffs[].file_path` (composite `Path.resolve()`) can differ in case/separator on Windows; route both through one helper. [type: defect] [source: pr70-cq-review-20260620] | M | items/refactor-transaction-path-format-unify.md |
| pyright-validate-position-redundant-read | Low | — | **`_validate_position` redundant full-file read** — reuse `ensure_file_open`'s content instead of a second `read_text` per call on the ~12-tool position hot path; negligible vs LSP cost (hygiene). [type: refactor] [source: pr71-cq-review-20260620] | S | items/pyright-validate-position-redundant-read.md |
| refactor-transaction-workspace-resolution | Low | — | **`refactor_transaction` ignores nested step paths for workspace resolution** — resolve the workspace from `steps[].args.file_path` instead of most-recent/CLI fallback; today a file in a non-most-recent workspace raises a confusing "outside workspace root". [type: defect] [source: pr70-coldreview-20260620] | S | items/refactor-transaction-workspace-resolution.md |

## Defer

<!-- Explicitly parked. Record WHY in the `do` cell. -->

| id | pri | deps | do | size | detail |
|----|-----|------|----|------|--------|
| cand-find-cyclic-imports | Defer | — | **Dedicated cycle report — parked as redundant** — `get_module_dependencies` already returns cycles; unblock only if per-edge provenance (file:line:col per import) is added as a real delta. [type: enhancement] [source: candidate-proposal] | — | items/cand-find-cyclic-imports.md |
| search-symbol-iter-dedup | Defer | — | **Extract shared search helpers — trigger fired, parked pending operator unblock** — `unused_symbols.py` duplicates 4 `dead_code.py` helpers; extraction spans ~5 prod files (split-candidate). [type: refactor] [source: handoff-prep-20260528] | — | items/search-symbol-iter-dedup.md |

## Refs

- `ai_docs/workflow.md` — execution flow and backlog closure rules
- `ai_docs/architecture.md` — current system architecture
- `ai_docs/items/` — per-row implementation detail (Anchors/Acceptance/Evidence); seed new files from `templates/items.md`
- `ai_docs/references/mcp_best_practices.md` — MCP design reference
- `../CI_POLICY.md` — merge gating policy
- `../audit-reports/application-brainstorm.md` — not-yet-sized product/refactor ideas (BRAIN-014..017 current) for brainstorm/planning intake; promote a BRAIN row to a sized backlog row when its first slice is ready
- `ai_docs/plans/20260527T205134Z_backlog-sweep/plan.md` — Backlog sweep (20260527T205134Z), completed 2026-05-29. Shipped 6 initiatives across 6 PRs (#50, #51, #52, #57, #58, #59); closed 6 backlog rows.
