# Backlog
<!-- purpose: Open follow-up work items only — remove entries when completed. -->
<!-- scope: in-repo -->

**updated_at:** 2026-04-24T23:00:00Z

## Agent contract

- This file contains **unfinished work only**. Remove or update rows when work ships.
- MUST NOT add completed-history sections or use the backlog as a changelog — `CHANGELOG.md` is the human-facing history, git history is the canonical record, and this backlog holds only open work.
- Implementation plans MUST include a final step: `backlog: sync ai_docs/backlog.md`.
- Release-affecting changes MUST add a bullet under `## [Unreleased]` in `CHANGELOG.md` in the same PR that ships the change.
- Each row has a stable `id` for grep-friendly referencing.

## Standing rules

- Best practices reference: `ai_docs/references/mcp_best_practices.md`.
- Historical plans, audits, and reports removed — originals preserved in git history.
- Priority tiers: Critical > High > Medium > Low > Defer.

## Open items

| id | priority | area | item | blocker |
|----|----------|------|------|---------|
| known-rope-annotations | Low | upstream | `change_signature` strips Python 3 type annotations during normalization (rope `ArgumentNormalizer`). Documented in `backends/rope_backend.py`. | rope upstream |
| cand-apply-lint-fixes | Medium | infrastructure | New tool `apply_lint_fixes` — ruff `--fix` wrapper; pairs with `get_diagnostics`/`find_errors_static` to close the auto-fix loop. | none |
| cand-find-type-users | Medium | search | New tool `find_type_users` — inverse of `find_references` scoped to a type: annotate/instantiate/subclass sites for a class or Protocol. Composition of existing `find_references` + Pyright type resolution. | none |
| cand-apply-type-annotations | Medium | refactoring | New tool `apply_type_annotations` — materialize inferred types (same source as `get_inlay_hints`) into real annotations; pairs with `get_type_coverage` for a closed-loop improvement. Requires a CST apply path. | custom-cst |
| cand-convert-to-dataclass | Low | refactoring | New tool `convert_to_dataclass` — modernize a plain class to a `@dataclass`; field types come from Pyright inference. Requires custom CST rewrite. | custom-cst |
| cand-extract-class | Low | refactoring | New tool `extract_class` — move a cohesive subset of fields/methods into a new collaborator class. **Rope 1.14 ships no `ExtractClass`** — requires custom CST implementation, not a rope wrapper. | custom-cst |
| cand-convert-function-method | Low | refactoring | Symmetric pair `convert_function_to_method` / `convert_method_to_function`. **No rope API** — custom CST with caller rewrite via `find_references`. | custom-cst |
| cand-split-module | Low | refactoring | New tool `split_module` — partition a single module into N modules by symbol selection. Rope `Move` exists but batch orchestration is custom. | custom-cst |
| cand-extract-superclass | Defer | refactoring | Earlier proposed wrapper over rope `ExtractSuperclass`. **Verified absent in rope 1.14.0** (`rope.refactor` ships no `extractsuperclass` module). Kept as Defer with `rope-api-absent` to prevent re-proposal; unblock only if a CST implementation is accepted in scope. | rope-api-absent |
| cand-find-cyclic-imports | Defer | analysis | Earlier proposed as a dedicated cycle report. **Redundant**: `get_module_dependencies` already returns `circular_dependencies: list[list[str]]` via `tools/metrics/dependencies.py::_find_cycles`. Kept as Defer to prevent re-proposal; unblock only if per-edge provenance (file:line:col of offending import) is added as a real delta. | redundant-with-get_module_dependencies |

## Refs

- `ai_docs/workflow.md` — execution flow and backlog closure rules
- `ai_docs/references/mcp_best_practices.md` — MCP design reference
