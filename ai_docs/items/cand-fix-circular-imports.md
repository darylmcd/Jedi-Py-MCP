# cand-fix-circular-imports — Auto-fix circular imports via TYPE_CHECKING hoist

**row:** `cand-fix-circular-imports` · **pri:** `Low` · **size:** `M` · **deps:** `module-dependency-cycle-accuracy`

## Anchors

- `src/python_refactor_mcp/tools/metrics/dependencies.py` (`get_module_dependencies` — cycle detection source)
- `src/python_refactor_mcp/util/cst_apply.py` (hoist edit + annotation stringification)
- new tool module + registration

## Acceptance

- [ ] Detector finds import cycles via `get_module_dependencies`, then for each cycle edge classifies imports as type-only (used solely in annotations) vs runtime.
- [ ] Type-only imports hoisted into an `if TYPE_CHECKING:` block; affected annotations stringified.
- [ ] Conservative bias on classification (false "type-only" breaks at import time); dry-run mandatory; change-stack rollback.
- [ ] Unit tests cover a 2-module cycle with a type-only edge and a mixed (type + runtime) edge that is left untouched.

## Evidence

- Circular-import bugs are a top-3 Python pain point; `get_module_dependencies` (cycle detection) + the LibCST apply foundation are both already present.

## Context

- Source brainstorm: BRAIN-004. Distinct from the deferred `cand-find-cyclic-imports` (a report-only idea) — this row *fixes* cycles, not just reports them. Risk: usage-site classification must be conservative (false negatives break at import time, not refactor time).
