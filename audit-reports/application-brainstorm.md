# Application Brainstorm Report

**Repo:** Jedi-Py-MCP
**Generated:** 2026-05-27 (Pass 2); updated 2026-05-28 (Pass 4 — BRAIN-011..013); updated 2026-05-28 (Pass 5 — BRAIN-014..017, ops + parity lanes); updated 2026-06-19 (Pass 6 — BRAIN-018..022 via discovery-sweep; BRAIN-018/021 promoted to backlog)
**HEAD at generation:** ba268b2a02def3fdc50004113cdf78e77295ee99
**HEAD at Pass 4 update:** 10b36070cb62e1e8826b51c70effc9461e561803
**HEAD at Pass 5 update:** 4c180c4e997a810a8675dfe2d1d8018e2ab1fe86
**HEAD at Pass 6 update:** 62f7d3905c92df56208db582c3faaa0f20541d4d
**last-run-HEAD:** 62f7d3905c92df56208db582c3faaa0f20541d4d
**Source prompt:** `C:/Users/daryl/.claude/prompts/application-brainstorm-prompt.md`
**Mode:** `mode=both record=auto web=auto` (Pass 5); market notes are local inference (no live browse)

> **Pass 5 note:** BRAIN-002 (`cand-unused-symbol-sweep`) and BRAIN-006 (`cand-test-impact-selector`) are currently in the **active re-prepared plan** `ai_docs/plans/20260527T205134Z_backlog-sweep/` (readyForExecute) — their backlog rows own implementation; do NOT re-promote. Pass 5 deliberately added ops/observability (BRAIN-016/017) and category-parity (BRAIN-014/015) ideas because Passes 2–4 were almost entirely net-new refactoring tools.
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

- **Status:** promoted
- **Horizon:** near
- **First slice:** Single-module `rename_symbol` variant that uses the existing LibCST apply foundation (introduced in #35) to rewrite `import X as Y` / `from m import X as Y` consistently across the project, where Jedi/Rope alone miss alias re-bindings.
- **Why now:** #35 landed the LibCST apply scaffold; #36 (apply_type_annotations) proved the end-to-end path. Rename is the highest-value CST-backed refactor that current `rename_symbol` (Rope-based) under-serves on alias-heavy codebases.
- **Risks / unknowns:** Conflict resolution when alias collides with existing binding in target scope; need rollback story tied to `begin_change_stack` / `rollback_change_stack`.
- **Cross-ref:** `cand-rename-cst-alias` (Low) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote.

## BRAIN-002 — Project-wide unused-symbol sweep tool

- **Status:** promoted
- **Horizon:** near
- **First slice:** Aggregate `dead_code_detection` across all project modules; emit a single ranked report keyed by `(module, symbol, kind)` with a "safe to delete" confidence score derived from `find_references` count + public-API membership.
- **Cross-ref:** `cand-unused-symbol-sweep` (Low) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote.
- **Notes:** Keep this BRAIN row for provenance and to track longer-horizon extensions (e.g., cross-project sweep once workspace-graph lands — see BRAIN-009).

## BRAIN-003 — Convert-to-dataclass / TypedDict / Pydantic model refactor

- **Status:** promoted
- **Horizon:** mid
- **First slice (promoted):** Detect "data-bag" classes (only `__init__` + attribute assignments, no behavior) and offer dataclass conversion with `@dataclass(frozen=...)` heuristic based on mutation analysis.
- **Cross-ref:** `cand-convert-to-dataclass` (Low) covers the dataclass slice; `cand-convert-typeddict-pydantic` (Low) covers the TypedDict + Pydantic v2 variants — both in `ai_docs/backlog.md`. Backlog rows own implementation; do NOT re-promote.
- **Remaining brainstorm scope:** none — TypedDict + Pydantic v2 variants promoted to `cand-convert-typeddict-pydantic`.

## BRAIN-004 — Auto-fix circular imports via TYPE_CHECKING hoist + deferred-string annotations

- **Status:** promoted
- **Horizon:** mid
- **First slice:** Detector pass that finds import cycles via `get_module_dependencies`, then for each cycle edge classifies imports as "type-only" (used solely in annotations) vs "runtime". Type-only imports get hoisted into `if TYPE_CHECKING:` block and annotations stringified.
- **Why now:** Circular-import bugs are a top-3 Python pain point; we already have `get_module_dependencies` + LibCST apply.
- **Risks / unknowns:** Requires confident usage-site classification — false negatives (treating a runtime use as type-only) break at import time, not at refactor time. Need conservative bias + dry-run mandatory.
- **Cross-ref:** `cand-fix-circular-imports` (Low) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote.

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

- **Status:** promoted
- **Horizon:** mid
- **First slice:** For projects that ship `.pyi` stubs alongside `.py` sources (or vendor third-party stubs), diff stub signatures vs implementation signatures and surface drift. Hook into `create_type_stubs` to regenerate.
- **Why now:** Adjacent to apply_type_annotations (#36); reuses signature-comparison logic.
- **Risks / unknowns:** Need to handle `@overload` and `Protocol` stubs without false-positive churn.
- **Cross-ref:** `cand-type-stub-freshness` (Low) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote.

## BRAIN-009 — Cross-project rename orchestrator hardened with workspace-graph topo-order

- **Status:** promoted
- **Horizon:** mid
- **First slice:** Extend `multi_project_rename` to build a dependency graph across registered projects (via `list_environments` + each project's import graph), then apply renames in reverse-topological order so downstream consumers are updated before upstream definitions change visible names. Currently the tool applies in arbitrary order, which can leave intermediate broken states.
- **Why now:** Real users hit this when refactoring across a monorepo of related projects.
- **Risks / unknowns:** Cycle handling between projects (rare but real); need a strict "abort on cycle, surface to operator" path.
- **Cross-ref:** `cand-cross-project-rename-topo` (Low) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote.

## BRAIN-010 — Performance hot-path detector

- **Status:** research
- **Horizon:** long
- **First slice:** none yet. Concept: combine `code_metrics` complexity scores with `find_references` fan-in to identify "high-complexity, high-call-frequency" functions as profiling candidates. Output is a ranked list, not a refactor — operator decides next step.
- **Why parked:** Static complexity + static fan-in is a weak proxy for runtime hotness. Real value would require runtime profile ingestion (e.g., `py-spy` / `cProfile` traces), which is out of scope for an LSP-shaped server. Defer until a clear request lands.

## BRAIN-011 — Security-finding autofix codemod

- **Status:** promoted
- **Horizon:** near
- **First slice:** `yaml.load → yaml.safe_load` rewrite (and inject a `SafeLoader` argument where a `Loader=` kwarg is absent), CST-backed via `util/cst_apply.py`, keyed off the SEC022 findings emitted by `tools/metrics/security.py`. Extend to SEC020/SEC021 (the deserialization findings) once the SEC022 path proves the pattern.
- **Why now:** `tools/metrics/security.py` already detects these patterns (`_DANGEROUS_ATTR_CALLS` maps `("yaml","load") → SEC022`, plus the SEC020/SEC021 deserialization codes) but emits findings only — there is no fixer. The LibCST apply foundation (`util/cst_apply.py`, #35) makes a targeted codemod feasible.
- **Non-overlap (verified):** Does NOT duplicate `apply_lint_fixes`. Ruff `UP` rules cover language modernization (e.g. `dict()` → `{}`), not the SEC* injection/deserialization patterns. `security.py` has no autofix counterpart anywhere in the tree.
- **Risks / unknowns:** `yaml.load` with an explicit non-safe `Loader=yaml.Loader` may be deliberate; need a conservative skip + operator surface. The SEC020/SEC021 deserialization calls have no safe drop-in replacement, so they can only warn/annotate, not auto-rewrite — scope the codemod to SEC022 first and treat the deserialization codes as a flag-only follow-up.
- **Cross-ref:** `cand-security-autofix` (Medium) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote.
- **Expansion seed:**
  - *Smallest planning question:* For SEC022, is rewriting to `yaml.safe_load(...)` always behavior-preserving, or must we preserve an explicit `Loader=` when one is already safe?
  - *Likely backlog slices:* (1) SEC022 `yaml.load`→`yaml.safe_load` CST codemod with dry-run + `begin/commit/rollback_change_stack`; (2) SEC020/SEC021 advisory annotation pass (no rewrite); (3) a `security_autofix` MCP tool that consumes `SecurityScanResult` and dispatches per-finding-code fixers.
  - *Supporting evidence:* `tools/metrics/security.py` (`_DANGEROUS_ATTR_CALLS`, `SecurityFinding`/`SecurityScanResult` in `models.py`), `util/cst_apply.py`, change-stack tools.
  - *Decision that makes it implementation-ready:* Confirm the SEC022-only first slice (excluding the deserialization codes) and the dry-run-mandatory + rollback contract.

## BRAIN-012 — Refactoring-transaction composite tool

- **Status:** promoted
- **Horizon:** mid
- **First slice:** A transaction wrapper in `tools/.../composite.py` (which currently holds only `diff_preview`) that accepts an ordered list of `(tool, args)` preview-mode calls, collects their `TextEdit` outputs, and applies all of them atomically inside a single change-stack — committing via `commit_change_stack` on success or unwinding via `rollback_change_stack` on any failure. All-or-nothing across N tools and multiple files.
- **Why now:** The change-stack primitives (`begin_change_stack` / `commit_change_stack` / `rollback_change_stack`) already exist, and most refactoring tools already support preview mode (`apply=False`). The missing piece is composition: today a multi-tool refactor is N independent applies with no shared atomicity, so a mid-sequence failure leaves a half-applied tree.
- **Risks / unknowns:** Edit conflicts between staged previews (two tools editing overlapping ranges) need detection before commit; previews computed against pre-transaction source may go stale if an earlier edit shifts line/column positions — need either re-preview after each staged edit or offset reconciliation. Define conflict-on-overlap as abort-and-rollback.
- **Cross-ref:** `cand-refactor-transaction` (Medium) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote.
- **Expansion seed:**
  - *Smallest planning question:* Are staged previews computed against the original source or the running (partially-edited) source — i.e. does the wrapper re-preview after each step, or reconcile offsets?
  - *Likely backlog slices:* (1) a `refactor_transaction` tool taking an ordered `(tool, args)` list, executing each in preview, and applying under one change-stack; (2) overlap/conflict detection across staged `TextEdit` sets with abort-on-conflict; (3) a structured transaction result (per-step status, applied/rolled-back, diff summary).
  - *Supporting evidence:* `tools/.../composite.py` (current `diff_preview` home), change-stack tools, the `apply=False` preview convention documented in the python-refactor MCP server instructions.
  - *Decision that makes it implementation-ready:* Pick the re-preview-per-step vs offset-reconciliation strategy and the conflict-handling contract (abort vs best-effort).

## BRAIN-014 — Structural find-and-replace codemod (`structural_replace`)

- **Status:** promoted
- **Horizon:** mid
- **Shape:** new-feature / category-parity
- **First slice:** A `structural_replace(pattern, replacement, file_paths, apply=False) -> RefactorResult` tool that reuses the AST-pattern matcher behind the existing `structural_search` to locate shaped matches, then rewrites each via the LibCST apply foundation (`util/cst_apply.py`), returning edits in preview mode by default. Scope slice 1 to single-metavariable rewrites (e.g. `logger.warn($X)` → `logger.warning($X)`).
- **Why now:** `structural_search` already implements the *find* half (AST-shaped matching); the LibCST apply scaffold (#35) implements safe *mutation*. The *replace* half is the missing complement and is the single headline parity gap against best-in-class structural-codemod tools (see Market notes). Highest-leverage net-new tool the current stack can support without new dependencies.
- **Risks / unknowns:** whether `structural_search`'s pattern syntax already exposes capture/metavariables reusable in a replacement template, or whether replace needs its own pattern parser; comment/format preservation on rewrite (LibCST handles this); overlapping matches; must be dry-run-first + change-stack rollback.
- **Cross-ref:** `cand-structural-replace` (Medium) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote. Distinct from BRAIN-011 (security-specific codemod) — this is the general structural engine BRAIN-011 could later dispatch through.
- **Expansion seed:**
  - *Smallest planning question:* Does `structural_search` expose capture/metavariables reusable in a replacement template, or must `structural_replace` define its own pattern→template binding?
  - *Likely backlog slices:* (1) single-metavariable structural rewrite via LibCST + change-stack, dry-run default; (2) multi-capture + guard predicates; (3) a saved/named codemod library consumable in batch.
  - *Supporting evidence:* `tools/search/structural_search`, `util/cst_apply.py` (`apply_cst_transformer`), change-stack tools, `RefactorResult` model.
  - *Decision that makes it implementation-ready:* pattern-syntax reuse vs a dedicated replace parser, and the overlap/conflict contract.

## BRAIN-015 — Annotation-preserving `change_signature` via LibCST

- **Status:** promoted
- **Horizon:** mid
- **Shape:** existing-feature-improvement (unblocks a documented limitation)
- **First slice:** A LibCST-backed path for `change_signature` (or sibling `change_signature_cst`) that does parameter rename/reorder/add/remove WITHOUT stripping PEP 484/585 annotations — the documented rope `ArgumentNormalizer` limitation. Slice 1: parameter rename + reorder preserving annotations and defaults on the definition and call sites, dry-run first.
- **Why now:** `ai_docs/architecture.md` Known Gaps #1 and backlog row `known-rope-annotations` (Low, parked as "no workaround in current rope") document a real, user-visible defect — `change_signature` silently drops type annotations. The LibCST foundation (#35) now provides exactly the workaround rope lacks, satisfying that row's Defer rationale. This is an unblock, not a net-new feature.
- **Risks / unknowns:** call-site rewriting across the project depends on `find_references` correctness; combining rope (call-site discovery) with LibCST (edit emission) must be done carefully; keyword-vs-positional and default-value handling.
- **Cross-ref:** `cand-change-signature-cst` (Medium) in `ai_docs/backlog.md` owns implementation; do NOT re-promote. It is the unblock path for backlog `known-rope-annotations` (Low) — coordinate, do not duplicate.
- **Expansion seed:**
  - *Smallest planning question:* Reimplement `change_signature` wholesale on LibCST, or keep rope for discovery and add a thin CST post-pass that re-attaches the annotations rope dropped?
  - *Likely backlog slices:* (1) annotation-preserving param rename; (2) reorder; (3) add/remove with default handling + call-site updates.
  - *Supporting evidence:* `backends/rope_backend.py` `change_signature` + its inline annotation caveat, `util/cst_apply.py`, `find_references`, architecture Known Gaps #1.
  - *Decision that makes it implementation-ready:* wholesale-CST vs CST-post-pass strategy.

## BRAIN-016 — Server health/status tool + backend-provenance surfacing

- **Status:** promoted
- **Horizon:** near
- **Shape:** ops / logging-diagnostics
- **First slice:** A read-only `server_status` MCP tool reporting: server version, loaded workspace roots, each backend's liveness (Pyright langserver reachable, Jedi importable, rope ready), degraded-mode flags, and the resolved `pyright-langserver` path. Pairs with surfacing per-result backend provenance (extend the existing `TypeInfo.source` pattern) so the calling agent can tell when a Jedi fallback — not Pyright — served a result.
- **Why now:** `architecture.md` documents real degraded modes (Pyright unavailable → Jedi fallback; `list_environments` may return empty) but the agent has no server-level way to *see* them — it just silently gets thinner results, which erodes trust in an autonomously-mutating tool. The ops/observability lane is absent from both the brainstorm history (Passes 2–4 were all refactoring features) and the backlog.
- **Risks / unknowns:** backend liveness probes must be cheap/non-blocking (no full request round-trip per call); keep environment-path disclosure within the local-only privacy stance (PRIVACY.md — no telemetry; local introspection is fine).
- **Cross-ref:** `cand-server-status` (Medium) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote. Adjacent to `restart_server` and `list_environments` (consume, don't replace).
- **Expansion seed:**
  - *Smallest planning question:* Can each backend's liveness be probed cheaply without issuing a real analysis request per backend?
  - *Likely backlog slices:* (1) `server_status` tool (version + workspace roots + per-backend up/down booleans); (2) a degraded-mode flag on responses when a fallback fired; (3) a uniform `source`/confidence field across the analysis tool surface.
  - *Supporting evidence:* `config.py` interpreter discovery order, `backends/*`, `TypeInfo.source`, `restart_server`, `list_environments`, architecture Known Gaps.
  - *Decision that makes it implementation-ready:* the liveness-probe shape (cached lifespan state vs on-demand ping).

## BRAIN-017 — Structured local operation log + support bundle

- **Status:** superseded
- **Superseded-by:** BRAIN-020 (its `server_status` co-dependency shipped in #64, unblocking the framing)
- **Horizon:** mid
- **Shape:** ops / logging-diagnostics
- **First slice:** none firm yet. Concept: an opt-in, local-only structured log of tool invocations (tool, args-summary, files touched, applied-vs-preview, backend used, duration, error) plus a `collect_support_bundle` action that bundles recent logs + a workspace/config snapshot for troubleshooting a misbehaving server.
- **Why parked / lower confidence:** partial overlap with `get_refactoring_history` (which records refactor mutations for undo) — must scope to the non-overlapping value: ALL tool calls including failures and non-refactor reads, for support/debugging rather than user-facing undo. `PRIVACY.md` mandates no telemetry, so this must be strictly opt-in + local + redaction-aware. Needs a log-format + retention decision before a first slice exists.
- **Cross-ref:** partial overlap `get_refactoring_history` (refactor-mutation subset) — note when promoting; do not duplicate the undo stack.
- **Next checkpoint:** revisit if a real "the server returned wrong/empty results and I can't tell why" support case lands, or alongside BRAIN-016 (health) which shares the diagnostics surface.

## BRAIN-018 — Structured error envelope at the MCP boundary (preserve backend class + error code)

- **Status:** promoted
- **Horizon:** near
- **Shape:** ops / logging-diagnostics
- **First slice:** Map each `BackendError` subclass (`PyrightError`/`JediError`/`RopeError`/`ConfigError`/`WorkspaceResolutionError`) to a stable string code and re-raise it from `_tool_error_boundary` carrying both the code and the human message, instead of the current bare `ValueError(str(exc))`. Message text stays identical; the code is additive.
- **Why now:** `errors.py` already defines the typed hierarchy, but `server.py` `_tool_error_boundary` collapses every subclass to `ValueError(str(exc))`, discarding the class + any actionable code before the calling agent sees it. The just-shipped `server_status` (#64) gives health visibility; typed per-call failures complete the diagnostics story so an agent can route recovery (restart on `PyrightError`, surface a config fix on `ConfigError`).
- **Risks / unknowns:** whether FastMCP's tool-error path can carry a structured `code`/`data` field without a protocol bump — kill criterion: if not, downgrade to message-prefix tagging.
- **Cross-ref:** `cand-structured-error-envelope` (Low) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote. Distinct from `server_status` (health, not per-call provenance) and `pyright-position-request-param-merge-guard` (input merge).

## BRAIN-019 — Generalize security_autofix into a per-code fixer dispatcher

- **Status:** plan-first
- **Horizon:** mid
- **Shape:** existing-feature-improvement / security
- **First slice:** A `SecurityFixer` protocol + registry: move the existing SEC022 (`yaml.load`→`yaml.safe_load`) rewrite behind it, add an advisory-annotation fixer for SEC010/011 (shell injection — no safe drop-in), and a dispatcher that consumes `SecurityScanResult` and routes each finding by `rule_id`. Deserialization codes (SEC020/021/023) stay flag-only.
- **Why now:** `security_autofix` (shipped #64) handles only SEC022 via a single LibCST transformer; `tools/metrics/security.py` already detects a far larger code set with no fixer dispatch. The dispatcher turns the scanner from detect-only into a remediation surface for the whole catalog.
- **Risks / unknowns:** most SEC codes have no behaviour-preserving auto-rewrite, so near-term payoff is mostly annotate+report; multi-finding atomic apply inherits the open `codemod-multifile-atomicity` gap.
- **Depends on:** `codemod-multifile-atomicity` (Low) — gate the multi-finding atomic-apply slice behind it.
- **Expansion seed:**
  - *Smallest planning question:* one-rule-per-call (sidesteps the atomicity gap for v1) vs atomic multi-finding apply (blocked on `codemod-multifile-atomicity`)?
  - *Likely backlog slices:* (1) `SecurityFixer` protocol + registry with SEC022 moved behind it; (2) advisory-annotation fixer for SEC010/011; (3) `SecurityScanResult`-consuming dispatcher with per-finding structured result; (4) atomic multi-finding apply once `codemod-multifile-atomicity` lands.
  - *Supporting evidence:* `tools/refactoring/security_autofix.py`, `tools/metrics/security.py` (`_DANGEROUS_CALLS`, `SecurityScanResult`), `util/cst_apply.py`, change-stack tools.
  - *Decision that makes it implementation-ready:* one-rule-per-call vs atomic-multi-finding for v1, and which codes are rewrite vs advisory-only.

## BRAIN-020 — Opt-in structured operation log + collect_support_bundle (BRAIN-017 successor)

- **Status:** plan-first
- **Horizon:** mid
- **Shape:** ops / logging-diagnostics
- **First slice:** An opt-in (config-gated, default OFF) in-memory ring buffer recording per tool call: tool name, redacted args-summary, files touched, apply-vs-preview, backend used, duration, error-class; exposed via a read-only `recent_operations` tool. Defer the on-disk `collect_support_bundle` to slice 2.
- **Why now:** evolves BRAIN-017 — its `server_status` co-dependency has now shipped (#64), clearing the main blocker. `server_status` gives point-in-time health but no history; `get_refactoring_history` records only refactor mutations for undo, not reads/failures/backend-used. When a tool returns thin/empty results (documented degraded mode: Pyright down → Jedi fallback), there is no after-the-fact record of which backend served the call.
- **Risks / unknowns:** `PRIVACY.md` mandates no telemetry → must be strictly opt-in + local + redaction-aware; whether `_tool_error_boundary` can observe the backend actually used without an extra probe.
- **Cross-ref:** supersedes BRAIN-017 (same idea, now unblocked). Partial overlap with `get_refactoring_history` — scope to the non-overlapping value (all calls incl. reads + failures, for support not undo).
- **Expansion seed:**
  - *Smallest planning question:* can `_tool_error_boundary` see which backend served a call (Pyright vs Jedi fallback) without an extra round-trip, or must each tool report its own `source`?
  - *Likely backlog slices:* (1) opt-in in-memory operation ring buffer + `recent_operations` read tool; (2) redaction contract honouring `PRIVACY.md`; (3) `collect_support_bundle` persisting log + `server_status` + config snapshot.
  - *Supporting evidence:* `server.py` `_tool_error_boundary` (timing already present), `server_status` (#64), `get_refactoring_history`/`HistoryEntry`, `PRIVACY.md`, `config.py`.
  - *Decision that makes it implementation-ready:* in-memory-only vs persisted bundle for v1, and the redaction guarantee.

## BRAIN-021 — Precise pytest node-ID resolution for test_impact_select

- **Status:** promoted
- **Horizon:** near
- **Shape:** existing-feature-improvement
- **First slice:** Resolve the enclosing class for a test caller and emit `<file>::<Class>::<method>` (reuse the class-name derivation already in `navigation/hierarchy.py`); leave parametrization to slice 2.
- **Why now:** `test_impact.py` (shipped #59) builds node IDs as `<file>::<name>`, and its own docstring states parametrized + nested-class tests are not resolved to pytest's collected IDs. A bare `<file>::<name>` does not match pytest's collected ID for a class method, so the emitted invocation list can mis-target tests — undercutting a tool whose whole value is precision.
- **Risks / unknowns:** whether call-hierarchy items reliably expose enclosing-class context cheaply — kill criterion: if not, document the limitation instead.
- **Cross-ref:** `cand-test-impact-nodeid-precision` (Low) in `ai_docs/backlog.md`. Backlog row owns implementation; do NOT re-promote.

## BRAIN-022 — Capabilities self-description tool (machine-readable tool/dry-run/contract manifest)

- **Status:** research
- **Horizon:** mid
- **Shape:** integration / devex
- **First slice:** none firm yet — research. Decide source of truth: derive a `describe_capabilities` manifest from the existing `ToolRecord` annotations (read-only vs mutating already encoded in `tool_registry.py`) at registration time, vs a hand-authored sidecar.
- **Why now / why parked:** the server registers ~97 tools with a preview/apply convention (`apply: bool`, default False) spread across ~30 signatures, but no machine-readable manifest a consuming agent can query to learn which tools mutate, support dry-run, their stability tier, or error codes. Lower confidence: MCP's native `tools/list` may already expose enough (mutate/preview flags) to make a bespoke tool redundant — kill criterion if so. The repeated tool-count/category-consistency gates (#64/#65) are evidence the surface metadata is reconciled by hand today.
- **Cross-ref:** none. Adjacent to `changelog-unreleased-tool-tally` (the manual-count pain this could automate) but distinct.

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
| BRAIN-001 | LibCST-backed safe rename across imports                     | promoted             | near    | `cand-rename-cst-alias`           |
| BRAIN-002 | Project-wide unused-symbol sweep                             | promoted             | near    | `cand-unused-symbol-sweep`        |
| BRAIN-003 | Convert-to-dataclass / TypedDict / Pydantic                  | promoted             | mid     | `cand-convert-to-dataclass`, `cand-convert-typeddict-pydantic` |
| BRAIN-004 | Auto-fix circular imports via TYPE_CHECKING hoist            | promoted             | mid     | `cand-fix-circular-imports`       |
| BRAIN-005 | Batch async-ification tool                                   | research             | long    | —                                 |
| BRAIN-006 | Test-impact selector                                         | promoted             | near    | `cand-test-impact-selector`       |
| BRAIN-007 | Docstring sync                                               | promoted             | near    | `cand-docstring-sync`             |
| BRAIN-008 | Type-stub freshness audit                                    | promoted             | mid     | `cand-type-stub-freshness`        |
| BRAIN-009 | Cross-project rename orchestrator (workspace-graph topo)     | promoted             | mid     | `cand-cross-project-rename-topo`  |
| BRAIN-010 | Performance hot-path detector (static complexity + fan-in)   | research             | long    | —                                 |
| BRAIN-011 | Security-finding autofix codemod (SEC022 yaml.load)          | promoted             | near    | `cand-security-autofix`           |
| BRAIN-012 | Refactoring-transaction composite tool                       | promoted             | mid     | `cand-refactor-transaction`       |
| BRAIN-013 | Import-graph layering-rule enforcer                          | rejected-superseded  | —       | shipped: `check_layer_violations` |
| BRAIN-014 | Structural find-and-replace codemod (`structural_replace`)   | promoted             | mid     | `cand-structural-replace`         |
| BRAIN-015 | Annotation-preserving `change_signature` via LibCST          | promoted             | mid     | `cand-change-signature-cst` (unblocks `known-rope-annotations`) |
| BRAIN-016 | Server health/status tool + backend-provenance              | promoted             | near    | `cand-server-status`              |
| BRAIN-017 | Structured local operation log + support bundle             | superseded           | mid     | superseded-by `BRAIN-020`         |
| BRAIN-018 | Structured error envelope at the MCP boundary                | promoted             | near    | `cand-structured-error-envelope`  |
| BRAIN-019 | Generalize security_autofix into per-code fixer dispatcher   | plan-first           | mid     | depends `codemod-multifile-atomicity` |
| BRAIN-020 | Opt-in operation log + collect_support_bundle                | plan-first           | mid     | supersedes `BRAIN-017`            |
| BRAIN-021 | Precise pytest node-IDs for test_impact_select               | promoted             | near    | `cand-test-impact-nodeid-precision` |
| BRAIN-022 | Capabilities self-description tool                           | research             | mid     | —                                 |

## Merge / dedupe rules (for future passes)

1. Match incoming ideas against existing BRAIN-NNN rows by title-similarity AND first-slice-similarity. If both match, update the existing row in-place (do not mint a new ID).
2. If an existing row is `promoted` and a new variant arrives that meaningfully extends scope beyond the promoted slice, append the extension to the row's "Remaining brainstorm scope" section — do not re-promote.
3. If an idea is superseded by a better framing, set `status: superseded` and add `Superseded-by: BRAIN-NNN` — never delete.
4. IDs are append-only and globally monotonic. Next available ID after this generation: **BRAIN-023**.
5. Rejected/superseded ideas live in the `## Rejected / Superseded` section with verified evidence so future passes do not re-propose shipped capabilities.
