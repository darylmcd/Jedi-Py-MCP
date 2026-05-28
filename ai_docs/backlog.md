# Backlog

<!-- purpose: Open work only. Single-table format. Sync rows on ship. -->
<!-- scope: in-repo -->

**updated_at:** 2026-05-28T18:38:30Z

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
|    |     |      |    |

## Medium

| id | pri | deps | do |
|----|-----|------|-----|
| refactor-tool-error-boundary-decomposition | Medium | none | Decompose the shared `_tool_error_boundary`/`_wrapped` closure (`src/python_refactor_mcp/server.py:180-272`; cyclomatic 24 / cognitive 45 / nesting 5 / ~90 LOC — repo's highest per code_metrics) into composable helpers: `_resolve_backends(ctx, kwargs)` (multi-ctx lookup + lazy root-fetch + primary-path extraction + registry lookup) and `_validate_params(kwargs, workspace_root)` (path + identifier validation); keep timing + `BackendError`→`ValueError` translation in a thin wrapper. Distinct from `server-tool-registration-table` (that collapses the per-tool wrappers; this targets the shared decorator internals) but edits the same file; `server-tool-registration-table` shipped 2026-05-28 (now unblocked). Also folds in the `_maybe_fetch_roots` debug-level error-swallow (`server.py:155-177`) by moving it into `_resolve_backends`. Anchors: `src/python_refactor_mcp/server.py:180-272`. Evidence: code_metrics 2026-05-28 discovery-sweep refactor pass (native F-01). |
| mypy-2x-migration | Medium | none | Bump `mypy>=1.13` to `mypy>=2.0` in `pyproject.toml`. Probe on 2026-05-27 surfaced **344 errors in 4 files** (concentrated in `src/python_refactor_mcp/server.py`) under `strict = true`. Three dominant patterns: (a) `MCPContext` treated as variable-not-type (mypy 2.x stricter about type-alias distinction) — ~80 hits; (b) `MCPContext?` has no attribute `"debug"` requiring Optional-narrowing — ~80 hits; (c) `Untyped decorator makes function untyped` for every `@mcp.tool` wrapper — ~80 hits. Existing override at `pyproject.toml:68-70` already disables `type-arg`/`unused-ignore` for `server.py` — the new errors are NOT covered. Fix at source (NO `# type: ignore` band-aids per Standing Directive #1): introduce a proper `MCPContext` type-alias via `TypeAlias` annotation, add `@mcp.tool` type stubs or a typed wrapper, narrow `ctx` reads. Anchors: `src/python_refactor_mcp/server.py`, `pyproject.toml:62-70`. Evidence: ai_docs/reports/upgrade-eligibility-2026-05-27.md Batch 4 probe; deferred from that batch as out-of-scope for a dep-bump PR. **Related**: `server-tool-registration-table` shipped 2026-05-28, introducing the `tool_registry.py` registration table — the mypy-2x typing work should build on that table (typed `ToolRecord`/registrar) rather than the old per-wrapper shape. |

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
| pyright-position-request-param-merge-guard | Low | none | `_position_request` in `src/python_refactor_mcp/backends/pyright_lsp.py` builds the LSP `{textDocument, position}` envelope then calls `params.update(extra_params)`, letting a caller clobber the `textDocument`/`position` keys. Latent only — the sole caller (`get_references`) passes just `context` — but harden by merging extras under the base envelope (base keys win) or rejecting reserved keys with a `ValueError`. Anchors: `src/python_refactor_mcp/backends/pyright_lsp.py` (`_position_request`). Evidence: surfaced during 2026-05-28 backlog-sweep wave-1 (PR #50). |
| changelog-tool-count-drift | Low | none | `CHANGELOG.md` `[Unreleased]` narrates the server surface at 89 tools (`format_code` 87→88, `apply_lint_fixes` 88→89), but the live server registers 91 `@mcp.tool` and `tests/unit/test_server.py` asserts `== 91` — a 2-tool narrative gap. Identify the two unbumped additions and align the CHANGELOG (or correct the baseline). Anchors: `CHANGELOG.md`, `src/python_refactor_mcp/server.py`, `tests/unit/test_server.py`. Evidence: observed during 2026-05-28 backlog-sweep wave-1 reconcile. |

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
