# Application Brainstorm Report

**Repo:** Jedi-Py-MCP
**Generated:** 2026-05-27 (Pass 2); updated 2026-05-28 (Pass 4 — BRAIN-011..013)
**HEAD at generation:** ba268b2a02def3fdc50004113cdf78e77295ee99
**HEAD at Pass 4 update:** 10b36070cb62e1e8826b51c70effc9461e561803
**Source prompt:** `C:/Code-Repo/dev-sync/prompts/application-brainstorm-prompt.md`
**Mode:** `mode=local record=auto` (Pass 4 promotion)
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

## BRAIN-011 — Security-finding autofix codemod

- **Status:** plan-first
- **Horizon:** near
- **First slice:** `yaml.load → yaml.safe_load` rewrite (and inject a `SafeLoader` argument where a `Loader=` kwarg is absent), CST-backed via `util/cst_apply.py`, keyed off the SEC022 findings emitted by `tools/metrics/security.py`. Extend to SEC020/SEC021 (the deserialization findings) once the SEC022 path proves the pattern.
- **Why now:** `tools/metrics/security.py` already detects these patterns (`_DANGEROUS_ATTR_CALLS` maps `("yaml","load") → SEC022`, plus the SEC020/SEC021 deserialization codes) but emits findings only — there is no fixer. The LibCST apply foundation (`util/cst_apply.py`, #35) makes a targeted codemod feasible.
- **Non-overlap (verified):** Does NOT duplicate `apply_lint_fixes`. Ruff `UP` rules cover language modernization (e.g. `dict()` → `{}`), not the SEC* injection/deserialization patterns. `security.py` has no autofix counterpart anywhere in the tree.
- **Risks / unknowns:** `yaml.load` with an explicit non-safe `Loader=yaml.Loader` may be deliberate; need a conservative skip + operator surface. The SEC020/SEC021 deserialization calls have no safe drop-in replacement, so they can only warn/annotate, not auto-rewrite — scope the codemod to SEC022 first and treat the deserialization codes as a flag-only follow-up.
- **Cross-ref:** none yet — promote when first-slice plan is written.
- **Expansion seed:**
  - *Smallest planning question:* For SEC022, is rewriting to `yaml.safe_load(...)` always behavior-preserving, or must we preserve an explicit `Loader=` when one is already safe?
  - *Likely backlog slices:* (1) SEC022 `yaml.load`→`yaml.safe_load` CST codemod with dry-run + `begin/commit/rollback_change_stack`; (2) SEC020/SEC021 advisory annotation pass (no rewrite); (3) a `security_autofix` MCP tool that consumes `SecurityScanResult` and dispatches per-finding-code fixers.
  - *Supporting evidence:* `tools/metrics/security.py` (`_DANGEROUS_ATTR_CALLS`, `SecurityFinding`/`SecurityScanResult` in `models.py`), `util/cst_apply.py`, change-stack tools.
  - *Decision that makes it implementation-ready:* Confirm the SEC022-only first slice (excluding the deserialization codes) and the dry-run-mandatory + rollback contract.

## BRAIN-012 — Refactoring-transaction composite tool

- **Status:** plan-first
- **Horizon:** mid
- **First slice:** A transaction wrapper in `tools/.../composite.py` (which currently holds only `diff_preview`) that accepts an ordered list of `(tool, args)` preview-mode calls, collects their `TextEdit` outputs, and applies all of them atomically inside a single change-stack — committing via `commit_change_stack` on success or unwinding via `rollback_change_stack` on any failure. All-or-nothing across N tools and multiple files.
- **Why now:** The change-stack primitives (`begin_change_stack` / `commit_change_stack` / `rollback_change_stack`) already exist, and most refactoring tools already support preview mode (`apply=False`). The missing piece is composition: today a multi-tool refactor is N independent applies with no shared atomicity, so a mid-sequence failure leaves a half-applied tree.
- **Risks / unknowns:** Edit conflicts between staged previews (two tools editing overlapping ranges) need detection before commit; previews computed against pre-transaction source may go stale if an earlier edit shifts line/column positions — need either re-preview after each staged edit or offset reconciliation. Define conflict-on-overlap as abort-and-rollback.
- **Cross-ref:** none yet — promote when first-slice plan is written.
- **Expansion seed:**
  - *Smallest planning question:* Are staged previews computed against the original source or the running (partially-edited) source — i.e. does the wrapper re-preview after each step, or reconcile offsets?
  - *Likely backlog slices:* (1) a `refactor_transaction` tool taking an ordered `(tool, args)` list, executing each in preview, and applying under one change-stack; (2) overlap/conflict detection across staged `TextEdit` sets with abort-on-conflict; (3) a structured transaction result (per-step status, applied/rolled-back, diff summary).
  - *Supporting evidence:* `tools/.../composite.py` (current `diff_preview` home), change-stack tools, the `apply=False` preview convention documented in the python-refactor MCP server instructions.
  - *Decision that makes it implementation-ready:* Pick the re-preview-per-step vs offset-reconciliation strategy and the conflict-handling contract (abort vs best-effort).

---

## Rejected / Superseded

### BRAIN-013 — Import-graph layering-rule enforcer

- **Status:** rejected-superseded
- **Horizon:** —
- **Rationale:** Already implemented at HEAD. `check_layer_violations` is a shipped MCP tool that "Check[s] import directions against declared layer ordering" — exactly the proposed capability.
- **Evidence (verified at HEAD `10b3607`):**
  - `src/python_refactor_mcp/tools/metrics/architecture.py:59` — `async def check_layer_violations(config, layers, file_paths=None) -> list[LayerViolation]`, docstring "Check import directions against declared layer ordering. ... Imports from lower layers to higher layers are violations."
  - `src/python_refactor_mcp/server.py:1534` — registered as an MCP tool.
  - `src/python_refactor_mcp/models.py:494` — `LayerViolation` model.
- **Disposition:** Do NOT re-propose. Recorded here so future brainstorm passes recognize this as shipped, not open.

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
| BRAIN-011 | Security-finding autofix codemod (SEC022 yaml.load)          | plan-first           | near    | —                                 |
| BRAIN-012 | Refactoring-transaction composite tool                       | plan-first           | mid     | —                                 |
| BRAIN-013 | Import-graph layering-rule enforcer                          | rejected-superseded  | —       | shipped: `check_layer_violations` |

## Merge / dedupe rules (for future passes)

1. Match incoming ideas against existing BRAIN-NNN rows by title-similarity AND first-slice-similarity. If both match, update the existing row in-place (do not mint a new ID).
2. If an existing row is `promoted` and a new variant arrives that meaningfully extends scope beyond the promoted slice, append the extension to the row's "Remaining brainstorm scope" section — do not re-promote.
3. If an idea is superseded by a better framing, set `status: superseded` and add `Superseded-by: BRAIN-NNN` — never delete.
4. IDs are append-only and globally monotonic. Next available ID after this generation: **BRAIN-014**.
5. Rejected/superseded ideas live in the `## Rejected / Superseded` section with verified evidence so future passes do not re-propose shipped capabilities.
