# Backlog

<!-- purpose: Open work only. Single-table format. Sync rows on ship. -->
<!-- scope: in-repo -->

**updated_at:** 2026-05-27T22:30:00Z

## Agent contract

| | |
|---|---|
| **Scope** | This file lists unfinished work only. It is not a changelog. |
| **MUST** | Remove or update backlog rows when work ships; do it in the same PR or an immediate follow-up. |
| **MUST** | End implementation plans with a final todo: `backlog: sync ai_docs/backlog.md`. |
| **MUST** | Use stable, kebab-case `id` values per open row. |
| **MUST** | Every row's `do` cell summarizes the current need + the concrete next deliverable. Include `Anchors:` (specific source file paths) when the row references code, and evidence (audit/retro/CI signal) when one exists. |
| **MUST** | Size every row to a single bounded initiative — ≤4 production files, ≤3 test files, one regression-test shape. Split heroic multi-bug rows into per-bug children before planning against them. |
| **MUST NOT** | Add `Completed`, `Shipped`, `Done`, `History`, or `Changelog` sections. Git is the archive. |
| **MUST NOT** | Leave done items in the open table. |
| **MUST NOT** | Use `### <id>` body sections per item. The table row IS the canonical form. Items needing long-form depth (more than ~10 lines) link to `ai_docs/items/<id>.md` from the `do` cell. |

## Standing rules

<!-- Ongoing practices, not deletable work items. -->

- **Reprioritize on each audit pass.** Stale priority order is a finding.
- **Keep rows planner-ready.** A row is ready when an agent can read it cold and start a plan: name the live anchors and the next concrete deliverable or investigation output.
- **Replace stale umbrella rows with concrete follow-ons** before planning against them.
- **Long-form audit evidence belongs in referenced reports**, not in this file. The `do` cell carries a one-line evidence summary plus the report path.
- **Weak-evidence flag.** When a row's signal is thin (single retro session, self-audit only, etc.) say so explicitly in the `do` cell ("Weaker evidence — N until external session reproduces").
- **Priority tiers:** Critical > High > Medium > Low > Defer.
- Best-practices reference: `ai_docs/references/mcp_best_practices.md`.
- See `workflow.md` → **Backlog closure** for close-in-PR expectations.

---

## Critical

<!-- Production-breaking or blocking work. Empty section is fine; keep the header. -->

| id | pri | deps | do |
|----|-----|------|-----|
|    |     |      |    |

## High

| id | pri | deps | do |
|----|-----|------|-----|
| server-tool-registration-table | High | none | `src/python_refactor_mcp/server.py` is 1574 lines, registering 91 `@mcp.tool` functions via ~80 identical 5-line wrappers (decorator → `_get_current_backends` → delegation → `ctx.debug`). Replace per-tool wrapper functions with a declarative registration table mapping tool name → `(annotations, callable, debug-format)` and a single registrar that builds the FastMCP tool from each record. Target: shrink server.py to <400 lines. Anchors: `src/python_refactor_mcp/server.py`, `src/python_refactor_mcp/tools/`. Evidence: refactor + work-search audits concur (2026-05-27 discovery-sweep). |
| backend-threaded-decorator | High | none | RopeBackend and JediBackend duplicate the same `def _work(): ... asyncio.wait_for(asyncio.to_thread(_work), timeout=self._timeout) ... try/except <Backend>Error from exc` shell in ~47 methods (30 in rope, 17 in jedi). Extract `@_threaded(timeout, error_cls, op_name)` decorator (or `_run_in_thread(self, fn, op_name, error_cls)` helper) in a new `src/python_refactor_mcp/backends/_threading.py` so each method body becomes just the rope/jedi call. Anchors: `src/python_refactor_mcp/backends/rope_backend.py`, `src/python_refactor_mcp/backends/jedi_backend.py`. Evidence: refactor audit (2026-05-27 discovery-sweep). |

## Medium

| id | pri | deps | do |
|----|-----|------|-----|
| pyright-lsp-position-request-helper | Medium | none | `src/python_refactor_mcp/backends/pyright_lsp.py` (1427 lines) has ~40 `textDocument/*` methods (get_definition, get_implementation, get_declaration, get_type_definition, …) following the identical 25-line `normalize_path → ensure_file_open → _request(method, textDocument+position) → error-check → dict\|list dispatch` pattern. Extract `_position_request(method, file_path, line, char, result_converter, *, on_unhandled)` helper that owns the open/request/error/result-shape boilerplate. Anchors: `src/python_refactor_mcp/backends/pyright_lsp.py`. Evidence: refactor audit (2026-05-27 discovery-sweep). |
| mypy-2x-migration | Medium | none | Bump `mypy>=1.13` to `mypy>=2.0` in `pyproject.toml`. Probe on 2026-05-27 surfaced **344 errors in 4 files** (concentrated in `src/python_refactor_mcp/server.py`) under `strict = true`. Three dominant patterns: (a) `MCPContext` treated as variable-not-type (mypy 2.x stricter about type-alias distinction) — ~80 hits; (b) `MCPContext?` has no attribute `"debug"` requiring Optional-narrowing — ~80 hits; (c) `Untyped decorator makes function untyped` for every `@mcp.tool` wrapper — ~80 hits. Existing override at `pyproject.toml:68-70` already disables `type-arg`/`unused-ignore` for `server.py` — the new errors are NOT covered. Fix at source (NO `# type: ignore` band-aids per Standing Directive #1): introduce a proper `MCPContext` type-alias via `TypeAlias` annotation, add `@mcp.tool` type stubs or a typed wrapper, narrow `ctx` reads. Anchors: `src/python_refactor_mcp/server.py`, `pyproject.toml:62-70`. Evidence: ai_docs/reports/upgrade-eligibility-2026-05-27.md Batch 4 probe; deferred from that batch as out-of-scope for a dep-bump PR. **Related**: bundles well with `server-tool-registration-table` (High) — that refactor collapses the 80 wrappers and would naturally introduce a typed registration shape. |

## Low

| id | pri | deps | do |
|----|-----|------|-----|
| known-rope-annotations | Low | rope upstream | `change_signature` strips Python 3 type annotations during normalization (rope `ArgumentNormalizer`). Documented limitation; no workaround in current rope. Anchors: `src/python_refactor_mcp/backends/rope_backend.py`. Evidence: documented inline at the call site. |
| cand-convert-to-dataclass | Low | none | New tool `convert_to_dataclass` — modernize a plain class to a `@dataclass`; field types come from Pyright inference. CST apply foundation now exists. Anchors: `src/python_refactor_mcp/util/cst_apply.py` (foundation), `src/python_refactor_mcp/backends/pyright_lsp.py` (type source). Weaker evidence — proposed candidate. |
| cand-extract-class | Low | none | New tool `extract_class` — move a cohesive subset of fields/methods into a new collaborator class. Verified: rope 1.14 ships no `ExtractClass`; this uses the in-repo CST foundation. Anchors: `src/python_refactor_mcp/util/cst_apply.py` (foundation). Weaker evidence — proposed candidate. |
| cand-convert-function-method | Low | none | Symmetric pair `convert_function_to_method` / `convert_method_to_function`. CST foundation exists; caller rewrites via `find_references`. Anchors: `src/python_refactor_mcp/util/cst_apply.py`, `src/python_refactor_mcp/tools/analysis/references.py`. Weaker evidence — proposed candidate. |
| cand-split-module | Low | none | New tool `split_module` — partition a single module into N modules by symbol selection. Use the batch variant of the CST foundation for the multi-file emit; rope `Move` may handle import rewrites for a v1. Anchors: `src/python_refactor_mcp/util/cst_apply.py` (`apply_cst_transformer_batch`), `src/python_refactor_mcp/backends/rope_backend.py`. Weaker evidence — proposed candidate. |
| cand-extract-superclass | Low | none | New tool `extract_superclass` — pull a member subset up into a new base class. Rope 1.14 ships no `ExtractSuperclass` (verified absent); implement via the in-repo CST foundation. Unparked 2026-05-27: PR #35 added `src/python_refactor_mcp/util/cst_apply.py`, satisfying the Defer condition ("CST implementation accepted in scope"). Anchors: `src/python_refactor_mcp/util/cst_apply.py`. Weaker evidence — proposed candidate. |
| cand-unused-symbol-sweep | Low | none | New tool `unused_symbol_sweep` (brainstorm BRAIN-002) — project-wide audit of exported + private members with zero inbound references. Distinct from existing `dead_code_detection` (sweep scope: full export surface, not just locals). Reuses existing `find_references` traversal. Anchors: `src/python_refactor_mcp/tools/analysis/references.py`, `src/python_refactor_mcp/tools/search/dead_code.py`. Weaker evidence — proposed candidate. |
| cand-test-impact-selector | Low | none | New tool `test_impact_select` (brainstorm BRAIN-006) — given a set of changed symbols, return the affected pytest node IDs via `call_hierarchy` traversal. Anchors: `src/python_refactor_mcp/tools/navigation/call_hierarchy.py`. Weaker evidence — proposed candidate. |
| cand-docstring-sync | Low | none | New tool `docstring_sync` (brainstorm BRAIN-007) — diff function signatures vs docstring params and auto-update Google / NumPy / Sphinx style. Anchors: TBD (likely under `src/python_refactor_mcp/tools/refactoring/`). Weaker evidence — proposed candidate. |

## Defer

<!-- Explicitly parked. Record WHY in the `do` cell. -->

| id | pri | deps | do |
|----|-----|------|-----|
| cand-find-cyclic-imports | Defer | needs-per-edge-provenance | Earlier proposed as a dedicated cycle report. Redundant: `get_module_dependencies` already returns `circular_dependencies: list[list[str]]` via `tools/metrics/dependencies.py::_find_cycles`. Parked to prevent re-proposal; unblock only if per-edge provenance (file:line:col of offending import) is added as a real delta. Dep refreshed 2026-05-27: CST foundation landing does NOT unblock this row (gap is per-import-statement anchors in `dependencies.py`, unrelated to CST). Anchors: `src/python_refactor_mcp/tools/metrics/dependencies.py`. |

## Refs

- `ai_docs/workflow.md` — execution flow and backlog closure rules
- `ai_docs/architecture.md` — current system architecture
- `ai_docs/references/mcp_best_practices.md` — MCP design reference
- `../CI_POLICY.md` — merge gating policy
