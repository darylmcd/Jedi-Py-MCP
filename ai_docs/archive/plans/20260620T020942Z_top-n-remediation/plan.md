# Top-N Remediation Plan — 20260620T020942Z

**Invocation:** `/top-n-remediation` (no args) → N defaults to **5**.
**Backlog snapshot:** `2026-06-19T21:58:15Z` · **HEAD:** `ad70314` · **baseline `just validate`:** 228 passed (green).
**Mode:** autonomous, immediate-land per row (serial). No `gate=ask`, no `resume`, no `contextPct`, no `budget-minutes`.

## Curation decisions

- **Plan-collision:** none. The sole plan `20260527T205134Z_backlog-sweep` is `phase=complete`, all 6 initiatives `merged` (terminal) → empty `OWNED_BY_ACTIVE_PLAN`.
- **Orphaned-PR sweep:** zero open PRs → no in-flight exclusions.
- **Selector picked the 5 Medium-tier rows** (no High rows exist; N=5 exhausted before the Low tier).
- **`mypy-2x-migration` REROUTED → `/backlog-sweep:prepare`** (not implemented this run). Index-only selector classed it shovel-ready, but its detail file's Evidence shows **344 strict-mode errors across 4 files + a major dep bump (mypy 1.x→2.x) + an unresolved decorator-typing design decision** (stubs vs typed wrapper, no clear default). That is effective-L + design-gated = sweep-shaped. Per Directive #6 (match change size to task value) it belongs in the planning pipeline, not an autonomous top-n implementer.
- **No backfill to 5.** The deterministic next row (`known-rope-annotations`) overlaps `cand-change-signature-cst` on the same `change_signature` default-value residual — converging two overlapping rows is itself a planning task (prep warned against running both). Padding to 5 would mean overlap entanglement or net-new feature work that dilutes "remediation." Shipping 4 clean Medium rows is valid (prompt: any count < N is valid).

## Selection

| id | rank | reasons | estimated file touches |
|----|------|---------|------------------------|
| refactor-tool-error-boundary-decomposition | 1 | Medium·S. Decompose the repo's highest-complexity closure (`_tool_error_boundary`/`_wrapped`, cyc 24/cog 45/nest 5) into `_resolve_backends` + `_validate_params`; bounded, code_metrics acceptance threshold. | 1 prod (`server.py`) + unit test |
| cand-refactor-transaction | 2 | Medium·M. New `refactor_transaction` tool — atomic multi-tool composite under one change-stack; primitives already exist; concrete acceptance + the one design micro-decision (re-preview vs offset) has a clear engineering default (re-preview against running source). | 3 prod (`tools/composite.py`, `backends/rope_backend.py`, `models.py`) + unit test + registry |
| pyright-position-out-of-range-guard | 3 | Medium·S. Bounds-check line/char in `_position_request` so position-read tools raise a structured "position out of range" error instead of returning silent empty (rope path already validates; Pyright path does not). | 1 prod (`backends/pyright_lsp.py`) + unit test |
| tool-position-base-convention-docs | 4 | Medium·M. State the 0-based (LSP) convention in the ~60 position-based tool descriptions; add a description-contains-convention regression test (mirrors the existing tool-count-drift gate). | 3 prod (`tool_registry.py`, `server.py`, `models.py`) + unit test |

## Per-row state lines

- refactor-tool-error-boundary-decomposition: **landed** (PR #69 squash 1b2cbb4; hosted CI Validate pass 2m35s; remote+local branch pruned; main clean)
- cand-refactor-transaction: **landed** (PR #70 squash 01c60e4; hosted CI pass 2m39s; 97→98 tools; branches pruned; main clean). Follow-ups to file: rollback_change_stack no-op bug (verified), overlap line-align (Medium), path-format unify (Low).
- pyright-position-out-of-range-guard: **landed** (PR #71 squash fc1a199; hosted CI pass 2m38s; branches pruned; main clean). Follow-up to file: _validate_position redundant disk read (Medium).
- tool-position-base-convention-docs: **landed** (PR #72 squash 9ac436b; hosted CI pass 2m43s; 40 line/char tools carry the shared 0-based phrase + drift-proof gate; branches pruned; main clean). Follow-up filed: position-convention-positions-list-tools (Medium).

## Skipped / rerouted

- mypy-2x-migration: **rerouted → /backlog-sweep:prepare** (effective-L + decorator-typing design decision + major dep bump).
- cand-find-cyclic-imports, search-symbol-iter-dedup: Defer (parked).
- All Low-tier rows: not reached (N exhausted at the Medium tier).

## Final step

- `backlog: sync ai_docs/backlog.md` — close each shipped row via `/close-backlog-rows <id>` (deletes row + `items/<id>.md`, bumps `updated_at`). Update `CHANGELOG.md [Unreleased]` for user-visible changes (esp. the new-tool count bump for `cand-refactor-transaction`).
- Append `## Retrospective` to this file before declaring complete.

## Retrospective

**Run:** `/top-n-remediation` (N=5 requested). **Shipped 4 rows** (all Medium-tier); `mypy-2x-migration` rerouted to `/backlog-sweep:prepare`; no backfill (valid count<N). Zero open PRs, clean tracking `main` at session end. Mode: serial, immediate-land per row.

### Shipped table

| row | PR | squash commit | gate evidence | per-row reviews |
|-----|----|--------------|---------------|-----------------|
| refactor-tool-error-boundary-decomposition | [#69](https://github.com/darylmcd/Jedi-Py-MCP/pull/69) | 1b2cbb4 | `just ci` 246 unit + 27 integ; hosted CI Validate 2m35s | spec ✓ / cq ✓ (1 low, no row) |
| cand-refactor-transaction | [#70](https://github.com/darylmcd/Jedi-Py-MCP/pull/70) | 01c60e4 | `just ci` 253 unit + 27 integ; hosted CI 2m39s | spec ✓ / cq ✓ (concern-2 resolved pre-review; mypy red caught + fixed forward) |
| pyright-position-out-of-range-guard | [#71](https://github.com/darylmcd/Jedi-Py-MCP/pull/71) | fc1a199 | `just ci` 257 unit + 27 integ; hosted CI 2m38s | spec ✓ / cq ✓ (low docstring fixed inline) |
| tool-position-base-convention-docs | [#72](https://github.com/darylmcd/Jedi-Py-MCP/pull/72) | 9ac436b | `just ci` 258 unit + 27 integ; hosted CI 2m43s | spec ✓ / cq ✓ (low comment fixed inline) |

Gate evidence: each row's `just ci` was run locally to green BEFORE push (full lint+pyright+mypy+unit+integration mirror); hosted CI re-confirmed on every PR. Row 2's `just ci` caught an `unused-ignore` mypy error that the implementer's `just validate` (no mypy) missed — fixed forward (ce01df1), re-greened. Baseline at HEAD ad70314: `just validate` 228 passed.

### Skipped / rerouted

- `mypy-2x-migration` → recommend `/backlog-sweep:prepare`. Effective-L (344 strict errors across 4 files) + major dep bump + unresolved decorator-typing design decision. Row annotated in backlog with the reroute note.
- Defer rows untouched: `cand-find-cyclic-imports`, `search-symbol-iter-dedup`.

### Budget usage (vs §Session budget ceilings, N=5)

- **Rows implemented:** 4 (≤5). 
- **Subagent spawns:** 15 (row-prep 1 + selector 1 + implementers 5 [row 2 used 2: impl + concern-2] + reviewers 8) vs ceiling ≈3×N+4 = 19. Within.
- **gh operations:** ~14 (4× [pr create + checks-watch + merge] + 2 pr list sweeps) vs ceiling ≈8×N = 40. Within.
- **Context pressure:** none observed (no compaction, no truncated returns). No checkpoint/`resume=` needed.

### Directive #3 call-outs filed (5 follow-up rows from review findings)

| id | pri | source |
|----|-----|--------|
| rollback-change-stack-noop | Medium | PR70 cq-review — `rollback_change_stack` nulls `_change_stack` without `pop_all()` (verified pre-existing bug) |
| refactor-transaction-overlap-line-align | Medium | PR70 cq-review — index-aligned overlap spans over-abort on whole-line insert/delete |
| position-convention-positions-list-tools | Medium | PR72 cq-review — `selection_range`/`test_impact_select` (positions-list) outside the phrase + gate |
| refactor-transaction-path-format-unify | Low | PR70 cq-review — `files_affected` vs `diffs[].file_path` format mismatch on Windows |
| pyright-validate-position-redundant-read | Low | PR71 cq-review — redundant warm-path full-file read on the ~12-tool position path |

Two Low findings were fixed INLINE in their own PRs rather than filed (PR71 docstring rope-parity overclaim; PR72 test-comment coverage overclaim) — comment-accuracy fixes needing no re-review.

**Process note (own-miss, Directive #7):** the chore PR (#73, docs-only) first FAILED hosted CI — the `test_no_server_wide_tool_count_drift` unit gate flagged a bare "98 tools" in `items/position-convention-positions-list-tools.md` (counts are policed outside `reference.md`/`backlog.md`; `plans/` is excluded). I'd run only `backlog-lint`, not the full suite, assuming "docs-only = safe." Fixed forward (removed the count), re-ran `just test` locally to green (258), re-pushed. Lesson: doc changes can trip doc-consistency unit gates — run the suite, not just the lint.

### Other observations (not new rows)

- `ai_docs/runtime.md:13` says **Repo class | Public** but `AGENTS.md` + `.ai-doc-audit.md` declare **private** — doc drift; a `/doc-audit` concern (surfaced to operator, not filed as a code row).
- Completed plan `ai_docs/plans/20260527T205134Z_backlog-sweep/` is a `/reconcile-plans` GC candidate (all 6 initiatives merged).
- CHANGELOG `[Unreleased]` line ("All now read 96") remains stale vs the live 98 — already tracked by the open `changelog-unreleased-tool-tally` row (no new row).
