# cand-structured-error-envelope — Structured error envelope at the MCP boundary

**row:** `cand-structured-error-envelope` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/errors.py` (`BackendError` → `PyrightError`/`JediError`/`RopeError`/`ConfigError`/`WorkspaceResolutionError`; add stable `code`)
- `src/python_refactor_mcp/server.py:144-231` (`_tool_error_boundary` collapses every `BackendError` to `ValueError(str(exc))`)

(Regression test in `tests/unit/test_server.py` — one assertion per backend class; see Acceptance.)

## Acceptance

- [ ] Each `BackendError` subclass carries a stable string code (e.g. `PYRIGHT_BACKEND`, `JEDI_BACKEND`, `ROPE_BACKEND`, `CONFIG`, `WORKSPACE_RESOLUTION`).
- [ ] `_tool_error_boundary` re-raises a `BackendError` via the MCP error type carrying both the code and the human message (additive; message text unchanged so existing assertions pass).
- [ ] Non-`BackendError` exceptions stay on the existing generic path.
- [ ] One unit test per backend class asserts the code propagates.

## Evidence

- opportunity-scan BRAIN-018 (2026-06-19, composite 27.5): `errors.py` defines a typed hierarchy but `_tool_error_boundary` discards the class + any code before the caller sees it. Builds on the just-shipped `server_status` (#64) — health visibility + typed failures complete the diagnostics story. See `audit-reports/application-brainstorm.md`.

## Context

- Distinct from `server_status` (health, not per-call failure provenance) and `pyright-position-request-param-merge-guard` (input merge). Kill criterion: if FastMCP cannot carry a structured `code`/`data` field, downgrade to message-prefix tagging.
