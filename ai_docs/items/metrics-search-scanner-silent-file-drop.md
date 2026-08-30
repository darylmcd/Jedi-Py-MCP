# metrics-search-scanner-silent-file-drop — test_map / unused / constructors scanners silently skip files

**row:** `metrics-search-scanner-silent-file-drop` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tools/metrics/test_map.py` (line 41)
- `src/python_refactor_mcp/tools/metrics/unused.py` (lines 65, 99)
- `src/python_refactor_mcp/tools/search/constructors.py` (lines 47, 123, 172)
- `tests/unit/test_search_tools.py`

## Acceptance

- [ ] `get_test_coverage_map`, the unused-symbol helpers, and the constructor-site search report per-file parse/read skips to the caller.
- [ ] Skip reporting reuses the existing `BackendFailure`/skipped-file shape.
- [ ] Unit test per tool proves an unparseable file produces a caller-visible skip.

## Evidence

- doc-audit bad-code-surfacing 2026-08-30. `test_map.py:41` and `constructors.py` `continue` past unparseable files; `unused.py:65` returns `set()` and `unused.py:99` returns `[]`, so a read failure is indistinguishable from "this module exports nothing".

## Context

- Third slice of the silent-file-drop family (see `security-scan-silent-file-drop`, `metrics-scanner-silent-file-drop`). Deliberately excluded: `navigation/hierarchy.py:{81,113}` and `navigation/outline.py:80` — those are best-effort positional/folding refinement helpers with a caller-side primary path, not result-dropping scanners.
