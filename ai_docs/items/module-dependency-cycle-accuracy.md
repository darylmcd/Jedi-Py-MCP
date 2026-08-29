# module-dependency-cycle-accuracy — Make cycle detection complete and package-aware

**row:** `module-dependency-cycle-accuracy` · **pri:** `Medium` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/tools/metrics/dependencies.py`
- `tests/unit/test_dependency_metrics.py`

## Acceptance

- [ ] Resolve absolute and relative imports against the importing module's package context, including `src/` layouts.
- [ ] Replace traversal-global cycle suppression with deterministic strongly-connected-component coverage so shared-node cycles are not silently omitted.
- [ ] Preserve source, resolved target, import name, and line evidence for every internal dependency edge.
- [ ] Unit tests cover a shared-node multi-cycle graph and a package cycle formed with relative imports.

## Evidence

- `_find_cycles` marks nodes globally visited, so a later distinct cycle through an already visited node can be skipped. `_resolve_module_to_file` receives no importing-file context and cannot resolve `from .` / `from ..` edges.

## Context

- This is a correctness prerequisite for `cand-fix-circular-imports`; an autofix cannot safely classify or rewrite cycle edges until the detector's graph is complete.
