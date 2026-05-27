# Application Brainstorm Report

**Repo:** Jedi-Py-MCP
**Generated:** 2026-05-27
**HEAD at generation:** ba268b2a02def3fdc50004113cdf78e77295ee99
**Source prompt:** `C:/Code-Repo/dev-sync/prompts/application-brainstorm-prompt.md`
**Mode:** `mode=local record=auto` (Pass 2 promotion)
**Canonical backlog:** `ai_docs/backlog.md`

## Purpose

Durable home for forward-looking product/strategy/refactor ideas that survived Pass 1 filtering (defer-overlap check, stack fit, evidence grounding). Backlog rows live in `ai_docs/backlog.md`; this file holds longer-horizon thinking that is not yet a sized, ready-to-ship row.

## Conventions

- Each idea is assigned a stable `BRAIN-NNN` ID. IDs are append-only — never renumber.
- Status values: `research` | `plan-first` | `implementation-ready` | `promoted` | `superseded` | `dropped`.
- Horizon: `near` (≤2 weeks once started) | `mid` (2–8 weeks) | `long` (>8 weeks or speculative).
- "First slice named" = a concrete, scope-bounded entry point exists. Required before promoting to backlog.
- When a brainstorm idea is promoted to a backlog row, mark `Cross-ref:` here pointing at the backlog candidate ID and flip status to `promoted` — do NOT delete the BRAIN row (preserves provenance and prevents re-promotion loops).
- Superseded rows stay in the file with `status: superseded` + a pointer to the replacing BRAIN-ID.

---

## BRAIN-001 — LibCST-backed safe rename across imports with alias-aware rewrites

- **Status:** plan-first
- **Horizon:** near
- **First slice:** Single-module `rename_symbol` variant that uses the existing LibCST apply foundation (introduced in #35) to rewrite `import X as Y` / `from m import X as Y` consistently across the project, where Jedi/Rope alone miss alias re-bindings.
- **Why now:** #35 landed the LibCST apply scaffold; #36 (apply_type_annotations) proved the end-to-end path. Rename is the highest-value CST-backed refactor that current `rename_symbol` (Rope-based) under-serves on alias-heavy codebases.
- **Risks / unknowns:** Conflict resolution when alias collides with existing binding in target scope; need rollback story tied to `begin_change_stack` / `rollback_change_stack`.
- **Cross-ref:** none yet — promote when first-slice plan is written.

## BRAIN-002 — Project-wide unused-symbol sweep tool

- **Status:** promoted
- **Horizon:** near
- **First slice:** Aggregate `dead_code_detection` across all project modules; emit a single ranked report keyed by `(module, symbol, kind)` with a "safe to delete" confidence score derived from `find_references` count + public-API membership.
- **Cross-ref:** `cand-unused-symbol-sweep` (Low) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote.
- **Notes:** Keep this BRAIN row for provenance and to track longer-horizon extensions (e.g., cross-project sweep once workspace-graph lands — see BRAIN-009).

## BRAIN-003 — Convert-to-dataclass / TypedDict / Pydantic model refactor

- **Status:** promoted (partial — dataclass slice only)
- **Horizon:** mid
- **First slice (promoted):** Detect "data-bag" classes (only `__init__` + attribute assignments, no behavior) and offer dataclass conversion with `@dataclass(frozen=...)` heuristic based on mutation analysis.
- **Cross-ref:** `cand-convert-to-dataclass` (Low) in `ai_docs/backlog.md` covers the dataclass slice. TypedDict and Pydantic variants remain in brainstorm — do NOT promote those without operator approval.
- **Remaining brainstorm scope:** TypedDict conversion for dict-shaped return values; Pydantic v2 model conversion for classes that already use type hints + validation logic.

## BRAIN-004 — Auto-fix circular imports via TYPE_CHECKING hoist + deferred-string annotations

- **Status:** plan-first
- **Horizon:** mid
- **First slice:** Detector pass that finds import cycles via `get_module_dependencies`, then for each cycle edge classifies imports as "type-only" (used solely in annotations) vs "runtime". Type-only imports get hoisted into `if TYPE_CHECKING:` block and annotations stringified.
- **Why now:** Circular-import bugs are a top-3 Python pain point; we already have `get_module_dependencies` + LibCST apply.
- **Risks / unknowns:** Requires confident usage-site classification — false negatives (treating a runtime use as type-only) break at import time, not at refactor time. Need conservative bias + dry-run mandatory.

## BRAIN-005 — Batch async-ification tool

- **Status:** research
- **Horizon:** long
- **First slice:** none yet — research phase. Needs (a) a corpus of real sync→async migrations to study patterns, (b) decision on whether to wrap blocking I/O via `asyncio.to_thread` vs require library-level async swap.
- **Why parked:** No first slice means not promotable per Standing Directive #1 (correct fix over quick fix — and we don't yet know what "correct" looks like here).
- **Next checkpoint:** Revisit if a user repo with substantial sync I/O lands as a test case.

## BRAIN-006 — Test-impact selector

- **Status:** promoted
- **Horizon:** near
- **First slice:** Given a changeset (file paths + symbol names), use `find_references` + `call_hierarchy` to compute the transitive set of test files that exercise the changed symbols. Emit a `pytest` invocation list.
- **Cross-ref:** `cand-test-impact-selector` (Low) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote.

## BRAIN-007 — Docstring sync

- **Status:** promoted
- **Horizon:** near
- **First slice:** Detect drift between function signatures (params, return type, exceptions raised per `trace_exception_flow` equivalent) and the docstring's documented contract. Emit warnings; optional auto-update for unambiguous cases (param added/removed/renamed).
- **Cross-ref:** `cand-docstring-sync` (Low) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote.

## BRAIN-008 — Type-stub freshness audit

- **Status:** plan-first
- **Horizon:** mid
- **First slice:** For projects that ship `.pyi` stubs alongside `.py` sources (or vendor third-party stubs), diff stub signatures vs implementation signatures and surface drift. Hook into `create_type_stubs` to regenerate.
- **Why now:** Adjacent to apply_type_annotations (#36); reuses signature-comparison logic.
- **Risks / unknowns:** Need to handle `@overload` and `Protocol` stubs without false-positive churn.

## BRAIN-009 — Cross-project rename orchestrator hardened with workspace-graph topo-order

- **Status:** plan-first
- **Horizon:** mid
- **First slice:** Extend `multi_project_rename` to build a dependency graph across registered projects (via `list_environments` + each project's import graph), then apply renames in reverse-topological order so downstream consumers are updated before upstream definitions change visible names. Currently the tool applies in arbitrary order, which can leave intermediate broken states.
- **Why now:** Real users hit this when refactoring across a monorepo of related projects.
- **Risks / unknowns:** Cycle handling between projects (rare but real); need a strict "abort on cycle, surface to operator" path.

## BRAIN-010 — Performance hot-path detector

- **Status:** research
- **Horizon:** long
- **First slice:** none yet. Concept: combine `code_metrics` complexity scores with `find_references` fan-in to identify "high-complexity, high-call-frequency" functions as profiling candidates. Output is a ranked list, not a refactor — operator decides next step.
- **Why parked:** Static complexity + static fan-in is a weak proxy for runtime hotness. Real value would require runtime profile ingestion (e.g., `py-spy` / `cProfile` traces), which is out of scope for an LSP-shaped server. Defer until a clear request lands.

---

## Index

| ID        | Title                                                        | Status               | Horizon | Cross-ref                         |
|-----------|--------------------------------------------------------------|----------------------|---------|-----------------------------------|
| BRAIN-001 | LibCST-backed safe rename across imports                     | plan-first           | near    | —                                 |
| BRAIN-002 | Project-wide unused-symbol sweep                             | promoted             | near    | `cand-unused-symbol-sweep`        |
| BRAIN-003 | Convert-to-dataclass / TypedDict / Pydantic                  | promoted (partial)   | mid     | `cand-convert-to-dataclass`       |
| BRAIN-004 | Auto-fix circular imports via TYPE_CHECKING hoist            | plan-first           | mid     | —                                 |
| BRAIN-005 | Batch async-ification tool                                   | research             | long    | —                                 |
| BRAIN-006 | Test-impact selector                                         | promoted             | near    | `cand-test-impact-selector`       |
| BRAIN-007 | Docstring sync                                               | promoted             | near    | `cand-docstring-sync`             |
| BRAIN-008 | Type-stub freshness audit                                    | plan-first           | mid     | —                                 |
| BRAIN-009 | Cross-project rename orchestrator (workspace-graph topo)     | plan-first           | mid     | —                                 |
| BRAIN-010 | Performance hot-path detector (static complexity + fan-in)   | research             | long    | —                                 |

## Merge / dedupe rules (for future Pass 2 runs)

1. Match incoming ideas against existing BRAIN-NNN rows by title-similarity AND first-slice-similarity. If both match, update the existing row in-place (do not mint a new ID).
2. If an existing row is `promoted` and a new variant arrives that meaningfully extends scope beyond the promoted slice, append the extension to the row's "Remaining brainstorm scope" section — do not re-promote.
3. If an idea is superseded by a better framing, set `status: superseded` and add `Superseded-by: BRAIN-NNN` — never delete.
4. IDs are append-only and globally monotonic. Next available ID after this generation: **BRAIN-011**.
