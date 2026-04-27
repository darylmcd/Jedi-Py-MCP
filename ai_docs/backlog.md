# Backlog

<!-- purpose: Open work only. Single-table format. Sync rows on ship. -->
<!-- scope: in-repo -->

**updated_at:** 2026-04-27T00:00:00Z

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
| cand-apply-type-annotations | Medium | custom-cst | New tool `apply_type_annotations` — materialize inferred types (same source as `get_inlay_hints`) into real annotations; pairs with `get_type_coverage` for a closed-loop improvement. Requires a CST apply path (no rope/Jedi equivalent). Anchors: `src/python_refactor_mcp/backends/pyright_lsp.py` (inlay hints source), `src/python_refactor_mcp/util/` (CST helpers). Weaker evidence — proposed candidate. |

## Low

| id | pri | deps | do |
|----|-----|------|-----|
| known-rope-annotations | Low | rope upstream | `change_signature` strips Python 3 type annotations during normalization (rope `ArgumentNormalizer`). Documented limitation; no workaround in current rope. Anchors: `src/python_refactor_mcp/backends/rope_backend.py`. Evidence: documented inline at the call site. |
| cand-convert-to-dataclass | Low | custom-cst | New tool `convert_to_dataclass` — modernize a plain class to a `@dataclass`; field types come from Pyright inference. Requires custom CST rewrite. Anchors: `src/python_refactor_mcp/util/` (CST helpers), `src/python_refactor_mcp/backends/pyright_lsp.py` (type source). Weaker evidence — proposed candidate. |
| cand-extract-class | Low | custom-cst | New tool `extract_class` — move a cohesive subset of fields/methods into a new collaborator class. Verified: rope 1.14 ships no `ExtractClass`; this is a custom CST implementation, not a rope wrapper. Anchors: `src/python_refactor_mcp/util/` (CST helpers). Weaker evidence — proposed candidate. |
| cand-convert-function-method | Low | custom-cst | Symmetric pair `convert_function_to_method` / `convert_method_to_function`. No rope API — custom CST with caller rewrite via `find_references`. Anchors: `src/python_refactor_mcp/util/`, `src/python_refactor_mcp/tools/references/`. Weaker evidence — proposed candidate. |
| cand-split-module | Low | custom-cst | New tool `split_module` — partition a single module into N modules by symbol selection. Rope `Move` exists but batch orchestration is custom. Anchors: `src/python_refactor_mcp/backends/rope_backend.py`, `src/python_refactor_mcp/tools/`. Weaker evidence — proposed candidate. |

## Defer

<!-- Explicitly parked. Record WHY in the `do` cell. -->

| id | pri | deps | do |
|----|-----|------|-----|
| cand-extract-superclass | Defer | rope-api-absent | Earlier proposed wrapper over rope `ExtractSuperclass`. Verified absent in rope 1.14.0 (`rope.refactor` ships no `extractsuperclass` module). Parked to prevent re-proposal; unblock only if a CST implementation is accepted in scope. Evidence: rope source inspection. |
| cand-find-cyclic-imports | Defer | redundant-with-get_module_dependencies | Earlier proposed as a dedicated cycle report. Redundant: `get_module_dependencies` already returns `circular_dependencies: list[list[str]]` via `tools/metrics/dependencies.py::_find_cycles`. Parked to prevent re-proposal; unblock only if per-edge provenance (file:line:col of offending import) is added as a real delta. Anchors: `src/python_refactor_mcp/tools/metrics/dependencies.py`. |

## Refs

- `ai_docs/workflow.md` — execution flow and backlog closure rules
- `ai_docs/architecture.md` — current system architecture
- `ai_docs/references/mcp_best_practices.md` — MCP design reference
- `../CI_POLICY.md` — merge gating policy
