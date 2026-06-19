# structural-search-silent-file-drop — Surface skipped files in structural_search

**row:** `structural-search-silent-file-drop` · **pri:** `Low` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/tools/search/structural.py:156-158,197` (`_scan_file` raw `read_text`/`cst.parse_module` with no BackendError wrap; `asyncio.gather(..., return_exceptions=True)` keeps only list results)

(Regression test in `tests/unit/test_structural_search.py` — see Acceptance.)

## Acceptance

- [ ] A file that cannot be read or parsed during structural_search surfaces a count or per-file note rather than being silently omitted.
- [ ] `files_scanned` reflects attempted-vs-succeeded, or skipped files are reported to the caller.

## Evidence

- refactor discovery-sweep (2026-06-19): `_scan_file` uses raw `read_text`/`parse_module`; `gather(return_exceptions=True)` then keeps only list results, so an unreadable/invalid file is invisibly excluded and `files_scanned` undercounts with zero diagnostic. Verified at HEAD 62f7d39.

## Context

- Distinct from `jedi-hierarchy-swallowed-exceptions` (`except: pass` sites in jedi_backend.py/hierarchy.py). `structural_search` is the read sibling of the shipped `structural_replace` (#66).
