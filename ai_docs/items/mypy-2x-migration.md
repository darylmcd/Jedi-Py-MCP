# mypy-2x-migration — Bump mypy to 2.x and fix strict-mode fallout at source

**row:** `mypy-2x-migration` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/server.py`
- `pyproject.toml:62-70` (mypy config + existing `server.py` override)

## Acceptance

- [ ] `pyproject.toml` requires `mypy>=2.0`.
- [ ] `mypy --strict` passes with 0 errors — no new `# type: ignore` band-aids (Standing Directive #1).
- [ ] `MCPContext` is a proper `TypeAlias`; `@mcp.tool` wrappers typed (stubs or typed wrapper); `ctx` reads Optional-narrowed.

## Evidence

- 2026-05-27 probe: 344 errors in 4 files under `strict = true` — see `ai_docs/reports/upgrade-eligibility-2026-05-27.md` Batch 4; deferred from that batch as out-of-scope for a dep-bump PR.

## Context

- Three dominant error patterns (~80 hits each): (a) `MCPContext` treated as variable-not-type (mypy 2.x stricter about type-alias distinction); (b) `MCPContext?` has no attribute `"debug"` — needs Optional-narrowing; (c) `Untyped decorator makes function untyped` for every `@mcp.tool` wrapper.
- Existing override at `pyproject.toml:68-70` disables `type-arg`/`unused-ignore` for `server.py`; the new errors are NOT covered by it.
- Related: `server-tool-registration-table` shipped 2026-05-28 introducing `tool_registry.py` — build the typing work on that table (typed `ToolRecord`/registrar), not the old per-wrapper shape.
