# cand-find-cyclic-imports — Parked: dedicated cycle report is redundant

**row:** `cand-find-cyclic-imports` · **pri:** `Defer` · **size:** `—`

## Anchors

- `src/python_refactor_mcp/tools/metrics/dependencies.py` (`_find_cycles`)

## Acceptance

- [ ] Unblock ONLY if per-edge provenance (file:line:col of the offending import statement) is added as a real delta over `get_module_dependencies`.

## Evidence

- `get_module_dependencies` already returns `circular_dependencies: list[list[str]]` via `tools/metrics/dependencies.py::_find_cycles` — a dedicated tool adds nothing.

## Context

- Parked to prevent re-proposal. Dep refreshed 2026-05-27: CST foundation landing does NOT unblock this row — the gap is per-import-statement anchors in `dependencies.py`, unrelated to CST. Unblock trigger recorded here because v15 `deps` cells accept backlog row ids only.
