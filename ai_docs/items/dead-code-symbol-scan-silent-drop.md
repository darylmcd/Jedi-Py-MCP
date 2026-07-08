# dead-code-symbol-scan-silent-drop — Silent per-item scan failures in dead_code/unused_symbol_sweep/get_module_dependencies

**row:** `dead-code-symbol-scan-silent-drop` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tools/search/dead_code.py:229-233` (`dead_code_detection` Phase 1 — `asyncio.gather(..., return_exceptions=True)`, kept only via `isinstance(diag_result, list)`)
- `src/python_refactor_mcp/tools/search/dead_code.py:252-259` (`dead_code_detection` Phase 2 — same shape over `_check_symbol`)
- `src/python_refactor_mcp/tools/search/unused_symbols.py:242-251` (`unused_symbol_sweep` — same shape over `_check_export_symbol`)
- `src/python_refactor_mcp/tools/metrics/dependencies.py:95-99` (`get_module_dependencies` — bare `except (SyntaxError, OSError): continue`, zero logging, file silently excluded from the graph)

## Acceptance

- [ ] `dead_code_detection` and `unused_symbol_sweep` (both return `PaginatedDeadCode`) surface a skipped/error count instead of silently dropping `gather(return_exceptions=True)` exceptions.
- [ ] `get_module_dependencies` surfaces which files failed to parse instead of silently excluding them from the dependency graph.
- [ ] No happy-path behaviour change.

## Evidence

- doc-audit bad-code-surfacing 2026-07-08: same regression shape as the already-tracked `structural-search-silent-file-drop` (which covers only `structural_search`), found in 3 additional tools whose result models (`PaginatedDeadCode`, `DependencyGraph`) carry no `files_scanned`/error-count field at all — callers get zero signal anything was skipped.

## Context

- Sibling row to `structural-search-silent-file-drop` — kept separate per the backlog's per-tool row-sizing rule rather than folding into one oversized cross-tool row.
