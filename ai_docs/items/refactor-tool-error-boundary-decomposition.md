# refactor-tool-error-boundary-decomposition — Decompose the shared `_tool_error_boundary`/`_wrapped` closure

**row:** `refactor-tool-error-boundary-decomposition` · **pri:** `Medium` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/server.py` — `:180-272` (`_tool_error_boundary`/`_wrapped`) and `:155-177` (`_maybe_fetch_roots` debug-level error-swallow — fold into `_resolve_backends`)

## Acceptance

- [ ] `_resolve_backends(ctx, kwargs)` helper extracted (multi-ctx lookup + lazy root-fetch + primary-path extraction + registry lookup); `_maybe_fetch_roots` swallow moved inside it.
- [ ] `_validate_params(kwargs, workspace_root)` helper extracted (path + identifier validation).
- [ ] Thin wrapper retains only timing + `BackendError`→`ValueError` translation.
- [ ] code_metrics on the wrapper drops below the prior cyclomatic 24 / cognitive 45 / nesting 5 hotspot.

## Evidence

- Repo's highest-complexity function per code_metrics (cyclomatic 24 / cognitive 45 / nesting 5 / ~90 LOC) — 2026-05-28 discovery-sweep refactor pass (native F-01).

## Context

- Distinct from `server-tool-registration-table` (shipped 2026-05-28; collapsed the per-tool wrappers) — this row targets the shared decorator internals. Same file, now unblocked.
