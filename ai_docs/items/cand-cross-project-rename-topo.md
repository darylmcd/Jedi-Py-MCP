# cand-cross-project-rename-topo — Cross-project rename in reverse-topological order

**row:** `cand-cross-project-rename-topo` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py` (`multi_project_rename` — current arbitrary apply order)
- `src/python_refactor_mcp/tools/metrics/dependencies.py` (per-project import graph)
- `list_environments` registration (registered-project enumeration)

## Acceptance

- [ ] `multi_project_rename` builds a dependency graph across registered projects and applies renames in reverse-topological order (downstream consumers updated before upstream definition names change).
- [ ] Cross-project cycle handling: abort and surface to operator (no silent partial apply).
- [ ] Dry-run-first; per-project result surfaced.
- [ ] Unit/integration test covers a 2-project A→B dependency where order matters.

## Evidence

- The tool currently applies in arbitrary order, which can leave intermediate broken states across a monorepo of related projects. This is a correctness fix, not a nicety.

## Context

- Source brainstorm: BRAIN-009. Kept `Low` because the cross-project monorepo scenario is narrower than single-project rename; raise priority if a real multi-project repro lands. Risk: inter-project cycles (rare but real) need a strict abort path.
