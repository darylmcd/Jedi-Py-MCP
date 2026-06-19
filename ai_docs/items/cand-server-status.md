# cand-server-status — Read-only server health/status tool + backend provenance

**row:** `cand-server-status` · **pri:** `Medium` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/config.py` (interpreter / `pyright-langserver` discovery order)
- `src/python_refactor_mcp/backends/` (Pyright / Jedi / rope liveness)
- `src/python_refactor_mcp/models.py` (`TypeInfo.source` — existing provenance pattern to generalize); new status result model
- new tool registration (consume, do not replace, `restart_server` / `list_environments`)

## Acceptance

- [ ] `server_status` (read-only) reports: server version, loaded workspace roots, per-backend up/down booleans, degraded-mode flags, resolved `pyright-langserver` path.
- [ ] Liveness probes are cheap/non-blocking (cached lifespan state or a light ping — no full analysis round-trip per call).
- [ ] Environment-path disclosure stays within the local-only privacy stance (PRIVACY.md).
- [ ] Unit test asserts shape + a simulated degraded (Pyright-down) state.

## Evidence

- `architecture.md` documents real degraded modes (Pyright unavailable → Jedi fallback; `list_environments` may return empty) but the agent has no server-level way to see them — it silently gets thinner results, eroding trust in an autonomously-mutating tool.

## Context

- Source brainstorm: BRAIN-016. First slice is the status tool only; the broader per-result `source`/confidence provenance field across the analysis surface is a follow-up (track separately to keep this row S).
