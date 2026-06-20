# Backlog sweep plan — 20260620T215105Z

**Generated:** 2026-06-20T21:51:05Z
**Backlog snapshot:** 2026-06-20T04:21:58Z
**Initiative count:** 1
**Anchor verification:** pending

## Selection note

Phase A shape pre-filter (Step 2a, STANDARD.md §Row-Shape Classification) refused 24 shovel-ready rows (size S/M, 0 strong/0 medium signals) → routed to `/top-n-remediation`. Only `mypy-2x-migration` is sweep-shaped (effective-L: 344 strict errors across 4 files + a decorator-typing design decision). The 9 net-new tool candidates are deferred for a roadmap decision (surface already at 98 tools).

<!-- BSWEEP:STATUS-TABLE BEGIN — generated from state.json; do not edit by hand -->
## Status (generated)

| # | id | status | PR | rows closed |
|---|----|--------|----|-------------|
| 1 | mypy-2x-migration | pending | — | mypy-2x-migration |
<!-- BSWEEP:STATUS-TABLE END -->

## Initiatives (in order)

### 1. mypy-2x-migration

| Field | Content |
|---|---|
| Diagnosis | Ground-truth re-probe (Directive #5) materially changes the picture from the 2026-05-27 evidence. **mypy 2.1.0 already passes with 0 errors on 75 source files** under the current `pyproject.toml` config — the 344-error estimate is stale; the typing work shipped incidentally via `server-tool-registration-table` (PR #52/#58 era). Without the existing `[[tool.mypy.overrides]]` block, mypy 2.1.0 surfaces 103 errors across exactly 2 files: 88 in `tool_registry.py` and 15 in `server.py` — all `[type-arg]`, plus 2 `[unused-ignore]`. Root cause: `MCPContext = Context  # type: ignore[type-arg]` assigns the bare unparameterized `Context` (`Generic[ServerSessionT, LifespanContextT, RequestT]`) without type args; mypy 2.x's stricter `type-arg` enforcement flags every use site. Correct fix (verified live under mypy 2.1.0): `MCPContext: TypeAlias = Context[Any, Any, Any]`, which passes strict with 0 errors and makes the override block unnecessary; the `# type: ignore[type-arg]` on each alias line becomes dead and must be removed (`unused-ignore` is on under strict). No `MCPContext` use exists outside these 2 modules (fanout: 15 + 88 refs, 0 elsewhere). The dev pin `mypy>=1.13` must bump to `mypy>=2.0`. |
| Approach | 1. `pyproject.toml`: change `"mypy>=1.13"` → `"mypy>=2.0"` in `[project.optional-dependencies] dev`; remove the dead `[[tool.mypy.overrides]]` block. 2. `server.py`: add `TypeAlias` to the typing import; change `MCPContext = Context  # type: ignore[type-arg]` → `MCPContext: TypeAlias = Context[Any, Any, Any]`; remove a now-dead `# type: ignore[index]` if `unused-ignore` flags it. 3. `tool_registry.py`: same TypeAlias change + import. No signatures change — `MCPContext` stays the param type name throughout, transparent to callers; FastMCP's `eval_str=True` signature path resolves `Context[Any, Any, Any]` identically at runtime. |
| Scope | Production files: 2 (`src/python_refactor_mcp/server.py`, `src/python_refactor_mcp/tool_registry.py`). Config: 1 (`pyproject.toml` — pin + override removal; infrastructure, not toward the Rule 3 prod cap). Test files: 0 — the `just ci` `mypy --strict` step is the regression gate. Rule 3 satisfied (2 prod files). |
| Tool policy | edit-only |
| Estimated context cost | 30000 |
| Risks | (1) `Context[Any, Any, Any]` fills all three params with `Any` — semantically equal to the current ignore; no stricter lifespan typing is introduced (a future row could tighten `LifespanContextT` to `MultiWorkspaceContext`). (2) The `# type: ignore[index]` removal is safe but confirm via `just ci`. (3) mypy 2.x may pull new transitive deps on a fresh `pip install -e ".[dev]"`; note in PR. (4) If `mcp`'s `Context` later changes its type-param arity, `Context[Any, Any, Any]` needs updating — the override block was more resilient, but the explicit alias is the cleaner default. |
| Validation | (1) `just ci` passes with 0 mypy errors under mypy 2.x. (2) `python -m mypy . ` (or `--strict src/`) → "Success: no issues found in 75 source files". (3) No surviving `[unused-ignore]`. (4) `pytest tests/unit tests/contract` green (no runtime impact). (5) `pyproject.toml` carries no `[[tool.mypy.overrides]]` block post-edit. |
| Performance review | N/A — correctness/typing fix, no hot-path changes. |
| CHANGELOG category | Maintenance |
| CHANGELOG entry (draft) | **Maintenance:** Bumped the mypy dev dependency to 2.x and replaced the `# type: ignore[type-arg]` suppression on `MCPContext` with a proper `TypeAlias = Context[Any, Any, Any]` in `server.py` + `tool_registry.py`; removed the now-unnecessary `[[tool.mypy.overrides]]` block from `pyproject.toml`. `mypy --strict` passes with 0 errors. Closes `mypy-2x-migration`. |
| Backlog sync | Close rows: [mypy-2x-migration]. |

