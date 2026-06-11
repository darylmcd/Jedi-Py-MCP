# search-symbol-iter-dedup — Extract shared search helpers from dead_code.py / unused_symbols.py

**row:** `search-symbol-iter-dedup` · **pri:** `Defer` · **size:** `—`

## Anchors

- `src/python_refactor_mcp/tools/search/dead_code.py`
- `src/python_refactor_mcp/tools/search/unused_symbols.py`
- `src/python_refactor_mcp/tools/search/_helpers.py` (new — extraction target)

## Acceptance

- [ ] Shared pieces public in `tools/search/_helpers.py`: `iter_module_level_symbols(path, *, skip_decorated: bool)`, `resolve_target_files(...)`, `is_test_file(...)`, `score_dead_code_confidence(...)`.
- [ ] Both `dead_code.py` and `unused_symbols.py` call the shared helpers; duplicated copies deleted.

## Evidence

- handoff-prep flag during 2026-05-28 re-prepare (plan 20260527T205134Z); trigger condition met by that plan's init 4 (`cand-unused-symbol-sweep` shipped).

## Context

- TRIGGER FIRED 2026-05-28: `unused_symbols.py` duplicates `dead_code.py`'s `_is_test_file`, `_resolve_target_files`→`_resolve_targets`, `_score_confidence`→`_confidence`, and `_iter_module_level_symbols`→`_iter_export_symbols` (minus the decorator guard).
- Cross-module reuse of the underscore-prefixed helpers is blocked by Pyright `reportPrivateUsage` — that is WHY `unused_symbols.py` copied them; the extraction must make the helpers public.
- ~5 production files (over the size cap) — split-candidate; still Defer-classed pending operator unblock.
