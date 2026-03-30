# MCP Server Audit Report

**Date:** 2026-03-30
**Server version:** Python Refactor MCP v0.3.0
**Tools tested:** 87 tools across 8 categories
**Test targets:** Self (MCP server codebase, ~10.7K LOC) + CLI-Inventory-Tool (42 source files, 20 test files)

---

## Summary

Of 87 tools, the majority function correctly. **23 issues** were identified across two codebases, ranging from crashes to incorrect results, missing data, and validation bugs.

---

## Issues

### Issue 1: `type: ignore` comments not suppressed in diagnostics

- **Tool:** `get_diagnostics`, `get_workspace_diagnostics`
- **Input:** Files with `# type: ignore` or `# pyright: ignore[reportCallIssue]` comments
- **Expected:** Diagnostics on suppressed lines should be filtered out
- **Actual:** Diagnostics are still reported even when `# type: ignore` (bare, no codes) is present on the offending line
- **Severity:** Incorrect result
- **Reproducibility:** Always
- **Details:** 4 `reportCallIssue` errors on `ImportOrganizer(project, resource)` lines in `rope_backend.py` persist despite `# type: ignore` comments. Tested with bare `# type: ignore`, `# type: ignore[call-arg]`, and `# pyright: ignore[reportCallIssue]` — none suppressed the diagnostic.

### Issue 2: `list_environments` returns empty results

- **Tool:** `list_environments`
- **Input:** No parameters (default project)
- **Expected:** Should detect `.venv/` directory and the Python 3.14 interpreter
- **Actual:** Returns `{"result": []}`
- **Severity:** Missing data
- **Reproducibility:** Always
- **Details:** The project has a `.venv` directory with Python 3.14. Jedi's environment detection may not be finding it, or the tool may not be passing the project path correctly. **Confirmed on second codebase** (CLI-Inventory-Tool) — same empty result, suggesting a systemic Jedi issue rather than a project-specific config problem.

### Issue 3: `autoimport_search` returns empty for known packages

- **Tool:** `autoimport_search`
- **Input:** `name="FastMCP"`
- **Expected:** Should find `mcp.server.fastmcp.FastMCP` since it's an installed dependency
- **Actual:** Returns `{"result": []}`
- **Severity:** Missing data
- **Reproducibility:** Always
- **Details:** The AutoImport cache may need explicit warming, or the rope project configuration may not include the venv's site-packages.

### Issue 4: `suggest_imports` returns empty for importable symbols

- **Tool:** `suggest_imports`
- **Input:** `symbol="Path"`, `file_path="server.py"` (where Path is already imported)
- **Expected:** Should return `from pathlib import Path` as a suggestion
- **Actual:** Returns `{"result": []}`
- **Severity:** Degraded / expected behavior
- **Reproducibility:** Always
- **Details:** May be by-design — if the symbol is already imported, Pyright may not suggest it. However, the tool should still work for files where the symbol is NOT imported.

### Issue 5: `find_unused_imports` requires `file_path` even in batch mode

- **Tool:** `find_unused_imports`
- **Input:** `file_paths=[...]` without `file_path`
- **Expected:** Should work with only `file_paths` parameter (batch mode)
- **Actual:** Pydantic validation error: `Field required [type=missing]` for `file_path`
- **Severity:** Incorrect validation (minor)
- **Reproducibility:** Always
- **Details:** The tool's Pydantic model requires `file_path` as mandatory even when `file_paths` is provided. Should make `file_path` optional when `file_paths` is given.

### Issue 6: `get_symbol_outline` on `root_path` returns excessively large results

- **Tool:** `get_symbol_outline`
- **Input:** `root_path="C:/Code-Repo/Jedi-Py-MCP/src/python_refactor_mcp"`
- **Expected:** Manageable paginated results
- **Actual:** 3,158,571 characters — exceeds maximum allowed tokens
- **Severity:** Performance / missing pagination
- **Reproducibility:** Always
- **Details:** When scanning a root path, the tool returns ALL symbols including from `.venv` site-packages. The `root_path` parameter should respect workspace boundaries or the tool should paginate by default. Even a targeted `file_paths` call on just 4 files produced 626K characters.

### Issue 7: `get_refactoring_history` always empty

- **Tool:** `get_refactoring_history`
- **Input:** No parameters
- **Expected:** Should show history of refactoring operations
- **Actual:** Returns `{"result": []}`
- **Severity:** Expected behavior (no rope refactorings were applied via the tool)
- **Reproducibility:** Always when no rope operations have been performed
- **Details:** This is by-design — the history only tracks rope-initiated refactorings, not manual file edits. Noted for documentation clarity.

### Issue 8: `call_hierarchy` broken for class methods

- **Tool:** `call_hierarchy`
- **Input:** Various class method positions across `PyrightLSPClient`, `RopeBackend`, `JediBackend` (8 attempts)
- **Expected:** Should return callers and callees for each method
- **Actual:** Returns empty name `""`, empty callers `[]`, empty callees `[]` for every class method tested
- **Severity:** Incorrect result (tool effectively non-functional for class methods)
- **Reproducibility:** Always
- **Details:** Tested on `_request`, `start`, `rename`, `get_references`, `initialize`, `get_help`, `infer_type`, `goto_definition` across all 3 backend classes. All returned `{"name":"","kind":"function",...}` with empty call chains. The tool may only work for module-level functions, not class methods.

### Issue 9: `project_search` completely non-functional

- **Tool:** `project_search`
- **Input:** Queries `"Handler"`, `"Backend"`, `"Manager"` (with `complete=False`)
- **Expected:** Should find matching symbols (search_symbols found 10, 17, and 1 results respectively)
- **Actual:** All 3 queries returned empty results `[]`
- **Severity:** Incorrect result (tool completely non-functional)
- **Reproducibility:** Always
- **Details:** Jedi's `Project.search()` appears to have an uninitialized or broken search index. The parallel `search_symbols` tool (which combines Pyright + Jedi) found results for the same queries, suggesting the Pyright backend works but Jedi's project search does not.

### Issue 10: `find_constructors` inconsistent — misses some class instantiations

- **Tool:** `find_constructors`
- **Input:** `class_name="PyrightLSPClient"`
- **Expected:** Should find instantiation at `server.py:195` (`PyrightLSPClient(config)`)
- **Actual:** Returns 0 results
- **Severity:** Incorrect result
- **Reproducibility:** Always for `PyrightLSPClient`; works correctly for `RopeBackend` (3 results) and `JediBackend` (2 results)
- **Details:** May be related to mixed-case "LSP" in the class name or the specific import pattern. The class IS instantiated but the tool does not find it.

### Issue 11: `get_context` incorrect for decorated functions

- **Tool:** `get_context`
- **Input:** Positions inside `@mcp.tool`-decorated functions in `server.py`
- **Expected:** Should report the enclosing function scope (e.g., `find_references`)
- **Actual:** Reports `module: server` instead of the enclosing function
- **Severity:** Incorrect result
- **Reproducibility:** Always for `@mcp.tool`-decorated functions; works correctly for nested closures
- **Details:** Jedi appears unable to track scope through decorator wrappers. Positions inside `_wrapped` closures correctly report `function: _wrapped`, but positions inside the outer decorated function body report module scope.

### Issue 12: `get_symbol_outline` reports nested `_work()` closures as module-level

- **Tool:** `get_symbol_outline`
- **Input:** `rope_backend.py`
- **Expected:** Inner `_work()` closures should appear as children of their enclosing method
- **Actual:** ~34 inner `_work()` functions appear at module level in the outline (lines 285-1027)
- **Severity:** Incorrect result (cosmetic)
- **Reproducibility:** Always
- **Details:** Pyright's document symbols may flatten nested function definitions. The `_work()` functions are closures defined inside async methods like `rename()`, `extract_method()`, etc., but appear as top-level siblings.

### Issue 13: `get_workspace_diagnostics` counts inconsistency after `restart_server`

- **Tool:** `get_workspace_diagnostics` + `restart_server`
- **Input:** Called `restart_server`, then `get_workspace_diagnostics`
- **Expected:** Consistent counts reflecting current file state
- **Actual:** First call after restart showed 10 files with errors (including navigation files that were already fixed). Second call showed correct 4 files.
- **Severity:** Degraded performance (stale cache)
- **Reproducibility:** Sometimes (first call after restart)
- **Details:** The first `get_workspace_diagnostics` call after `restart_server` may return stale results. A second call returns the correct state. Pyright may need time to re-analyze after restart.

### Issue 14: `code_metrics` reports `lines_of_code` as 0 for all functions

- **Tool:** `code_metrics`
- **Input:** All 49 source files (383 functions analyzed)
- **Expected:** Each function should have a non-zero LOC count
- **Actual:** `lines_of_code` field is 0 for every function, while `loc` field has correct values
- **Severity:** Incorrect result (data field)
- **Reproducibility:** Always
- **Details:** The tool reports `loc` correctly (e.g., 47 for `_convert_document_symbol`) but the `lines_of_code` field is always 0. Appears to be a field mapping bug — the correct data exists but is in a different field name.

### Issue 15: `check_layer_violations` scans third-party packages and matches stdlib names

- **Tool:** `check_layer_violations`
- **Input:** `layers=[["tools"], ["backends"], ["util", "models", "config", "errors"]]`
- **Expected:** Should only scan project source files and match against project module names
- **Actual:** Returned 21 violations — 20 from `.venv` third-party packages, 1 from `lsp_client.py` importing `itertools` (stdlib)
- **Severity:** Incorrect result
- **Reproducibility:** Always
- **Details:** The tool scans `.venv/` packages (pydantic, libcst, jedi, httpcore) and matches stdlib module names like `itertools`, `functools` against layer keywords. Layer matching is doing substring matching on module names rather than scoping to the project's own package structure. Zero actual layer violations exist in project source.

### Issue 16: `find_errors_static` high false-positive rate

- **Tool:** `find_errors_static`
- **Input:** `pyright_lsp.py`, `rope_backend.py`
- **Expected:** Should find real static errors comparable to Pyright
- **Actual:** Returns 43 errors for `pyright_lsp.py` (vs Pyright's 2), 10 for `rope_backend.py` (vs Pyright's 16). ~80% of rope's findings are false positives from inability to resolve dict/set attributes and list comprehension variables
- **Severity:** Degraded (noisy results)
- **Reproducibility:** Always
- **Details:** Rope's static analysis flags `dict.clear()`, `dict.get()`, `dict.values()` as "unresolved attribute" because it can't infer dict types. List comprehension variables are flagged as "unresolved variable". Only ~20% of findings overlap with genuine Pyright errors. The tool is much less reliable than `get_diagnostics` for this codebase. **Confirmed on second codebase** (CLI-Inventory-Tool) — 86 false positives in a 445-LOC function where Rope cannot track variable definitions through complex control flow. Variables defined early in `main()` are flagged as "unresolved" hundreds of lines later; loop variables (`d`, `device`, `result`) defined in `for` headers are flagged with "Defined later" warnings.

### Issue 17: `security_scan` results vary depending on file scope

- **Tool:** `security_scan`
- **Input:** 5 backend files (Phase 6) vs all 49 source files (Phase 2 agent)
- **Expected:** Consistent results regardless of scope
- **Actual:** Scanning 5 backend files returned 0 findings; scanning all 49 files found 1 HIGH finding (`eval()` in `structural.py:83`)
- **Severity:** Cosmetic (not a bug — the `eval()` is in a file not included in the 5-file scan)
- **Reproducibility:** N/A (expected behavior, noted for completeness)
- **Details:** The `eval()` in `structural_search.py` is deliberate (LibCST pattern matching with restricted builtins) and has `# noqa: S307`. Worth documenting that security_scan correctly detects it.

### Issue 18: `relatives_to_absolutes`, `froms_to_imports`, `handle_long_imports` crash with ImportOrganizer error

- **Tools:** `relatives_to_absolutes`, `froms_to_imports`, `handle_long_imports`
- **Input:** Any file path with `apply=False`
- **Expected:** Preview of import conversion/reformatting
- **Actual:** `Error: ImportOrganizer.__init__() takes 2 positional arguments but 3 were given`
- **Severity:** Crash (3 tools completely broken)
- **Reproducibility:** Always
- **Details:** All three tools share the same ImportOrganizer code path in `rope_backend.py`. Root cause is a Rope API version mismatch — the constructor is being called with an extra argument. This blocks 3 of 8 import-related refactoring tools. Tested on CLI-Inventory-Tool's `config.py` and `ssh_phases.py`.

### Issue 19: `find_implementations` crashes for Protocol types

- **Tool:** `find_implementations`
- **Input:** `file_path="...models.py", line=45, character=6` (NetmikoConnection Protocol)
- **Expected:** List of concrete classes implementing the Protocol
- **Actual:** `Error: Implementation request failed: {'code': -32601, 'message': 'Unhandled method textDocument/implementation'}`
- **Severity:** Crash (unhandled LSP error)
- **Reproducibility:** Always (for Protocol types)
- **Details:** Pyright does not support `textDocument/implementation` for structural (Protocol) types. The MCP server should catch this error gracefully and return an empty result or fall back to a reference-based search.

### Issue 20: `suggest_imports` returns incorrect import for top-level packages

- **Tool:** `suggest_imports`
- **Input:** `symbol="pytest", file_path="...test_config_extended.py"`
- **Expected:** `import pytest`
- **Actual:** `from pytest import pytest` (incorrect — pytest is a package, not a name within itself)
- **Severity:** Incorrect result
- **Reproducibility:** Always (for top-level package names like `pytest`)
- **Details:** When the symbol IS the package name, the tool generates `from {symbol} import {symbol}` instead of `import {symbol}`. The generated import would fail at runtime. Distinct from Issue 4 (empty results) — this is an actively wrong result.

### Issue 21: `get_keyword_help` off-by-one line number

- **Tool:** `get_keyword_help`
- **Input:** `line=319, character=4` (where `with` keyword appears on file line 319)
- **Expected:** Keyword documentation for `with`
- **Actual:** Empty result `entries: []`
- **Workaround:** Calling with `line=318` (line-1) returns correct results
- **Severity:** Incorrect result (position mapping error)
- **Reproducibility:** Always
- **Details:** The tool appears to use 0-indexed line numbers internally while all other MCP tools use 1-indexed (matching file display). This creates a systematic off-by-one error for every call.

### Issue 22: `structural_search` does not return `files_scanned` field

- **Tool:** `structural_search`
- **Input:** Various patterns (`m.ExceptHandler(type=None)`, `m.Call(func=m.Name("print"))`, etc.)
- **Expected:** Response includes `files_scanned` count (as documented)
- **Actual:** Response does not include a `files_scanned` field
- **Severity:** Missing data
- **Reproducibility:** Always
- **Details:** The tool description says "Check `files_scanned` in the response to distinguish found-nothing from failed-to-scan", but the field is not present in actual responses. Makes it impossible to distinguish "no matches" from "scan failure".

### Issue 23: `find_unused_imports` false positives on `__all__` re-export facades

- **Tool:** `find_unused_imports`
- **Input:** `file_path="...config.py"` (a facade module using `__all__` to re-export imports)
- **Expected:** No unused imports (all are re-exports listed in `__all__`)
- **Actual:** 8 "unused" imports reported (all 8 are intentional re-exports)
- **Severity:** Degraded behavior (false positives)
- **Reproducibility:** Always (for files using the `__all__` re-export pattern)
- **Details:** The tool does not account for `__all__` when determining import usage. Imports that exist solely for re-export are flagged as unused. This is a common Python pattern (facade modules) that should be handled correctly. Distinct from Issue 5 (validation bug) — this is a semantic analysis gap.

---

## Cross-Tool Consistency Checks

| Check | Result |
|-------|--------|
| `get_diagnostics` vs `get_workspace_diagnostics` counts | **Consistent** across both codebases |
| `get_diagnostics` vs `get_syntax_errors` on syntax | **Consistent** — no false positives from either |
| `get_diagnostics` vs `find_errors_static` | **Inconsistent** — Rope reports many false positives that Pyright correctly handles (see Issues 16, confirmed on second codebase) |
| `find_references` vs `find_constructors` | **Consistent** — constructor sites are subset of references |
| Pre-restart vs post-restart diagnostics | **Consistent** on second call (first call may be stale, see Issue 13) |
| `search_symbols` vs `project_search` | **Different scope** — search_symbols does substring/fuzzy across both backends; project_search does exact Jedi match (project_search broken, see Issue 9) |

---

## Tools Verified Working Correctly

The following tools were tested and produced correct results:

### Analysis
- `get_diagnostics` — Correctly reported all Pyright errors with accurate line numbers and codes (confirmed on both codebases)
- `get_workspace_diagnostics` — Consistent aggregated counts (confirmed on both codebases)
- `get_type_info` — Correctly identified class types and docstrings (confirmed on both codebases)
- `get_type_coverage` — Accurately reported annotation coverage (confirmed on both codebases)
- `get_documentation` — Complete docstrings and signatures returned
- `get_completions` — Returned reasonable completions at cursor positions (some auto-import noise from `winreg`)
- `get_signature_help` — Excellent results: correct parameter names, types, active parameter index, and documentation
- `get_syntax_errors` — Correctly reported 0 syntax errors on files with only semantic issues (confirmed on both codebases)
- `get_context` — Correctly identified enclosing scopes (for non-decorated functions; see Issue 11)
- `simulate_execution` — Returned reasonable types via Jedi
- `find_unused_imports` — Correctly found 0 unused imports on clean codebase (has __all__ false positives, see Issue 23)

### Navigation
- `goto_definition` — Correctly resolved definitions across modules (confirmed on both codebases)
- `get_declaration` — Consistent with `goto_definition` results (expected per docs)
- `get_symbol_outline` — Complete hierarchical outlines for all files (has nesting issue, see Issue 12)
- `call_hierarchy` — Correct caller/callee chains for module-level functions (broken for class methods, see Issue 8)
- `get_module_public_api` — Correctly returned empty for `__init__.py` with no exports
- `type_hierarchy` — Correctly showed no supertypes/subtypes for concrete backend classes (confirmed on both codebases)
- `find_references` — Correctly found all references with accurate counts (confirmed on both codebases)

### Metrics & Architecture
- `code_metrics` — Correctly computed CC, cognitive complexity, nesting for 383 functions (LOC field has a mapping issue, see Issue 14)
- `get_module_dependencies` — Correctly detected 30 modules, 311 deps, 0 circular deps
- `get_coupling_metrics` — Correctly computed Ca/Ce/Instability following Stable Dependencies Principle
- `get_type_coverage` — Correctly reported 100% annotation coverage (383 functions, 870 params)
- `dead_code_detection` — Found 69 items (exclude_tests=true), 88 items (exclude_tests=false). ~60% are true dead code or actionable
- `find_duplicated_code` — Correctly found 0 duplicates across all 49 files
- `security_scan` — Correctly found 1 HIGH finding (`eval()` in structural_search.py) across all files
- `get_test_coverage_map` — Correctly mapped 555 symbols, 115 with test references (20.7%)
- `get_workspace_diagnostics` — Correctly aggregated error counts per file (after cache warmup)

### Refactoring
- `restart_server` — Successfully restarted Pyright and refreshed diagnostics (confirmed on both codebases)
- `organize_imports` — Correctly reported "already organized" on clean files
- `fix_module_names` — Correctly reported no PEP 8 violations
- `prepare_rename` — Correctly returned null for non-renameable positions
- `use_function` — Correctly reported limitations (e.g., "more than one return statement")

### Search
- `search_symbols` — Correctly found results across workspace (confirmed on both codebases)
- `structural_search` — Correctly found pattern matches (missing `files_scanned` field, see Issue 22)
- `find_constructors` — Worked correctly for most classes (inconsistent for some, see Issue 10)
- `find_duplicated_code` — Correctly identified duplications
- `get_folding_ranges` — Correctly returned folding ranges
- `dead_code_detection` — Reasonable results with appropriate confidence levels (confirmed on both codebases)

---

## Recommendations

### P1 — Broken functionality (crashes / non-functional)
1. **Fix ImportOrganizer crash** (Issue 18) — Update the Rope integration to match the current `ImportOrganizer` API. This blocks 3 of 8 import-related tools (`relatives_to_absolutes`, `froms_to_imports`, `handle_long_imports`).

2. **Fix `call_hierarchy` for class methods** (Issue 8) — Returns empty results for all class methods tested. Investigate whether Pyright's `callHierarchy/prepare` LSP request is being sent with correct positions for methods inside classes.

3. **Fix `project_search`** (Issue 9) — Jedi's `Project.search()` returns empty for all queries. Ensure the Jedi project is properly initialized with the workspace root and that the search index is built.

4. **Graceful fallback for `find_implementations`** (Issue 19) — Catch the `-32601` LSP error for Protocol types and return empty results or fall back to reference-based search.

5. **Fix `find_constructors` for all class names** (Issue 10) — Investigate why `PyrightLSPClient` returns 0 results while `RopeBackend` and `JediBackend` work correctly. May be a case-sensitivity or acronym-handling issue.

### P2 — Incorrect/degraded results
6. **Fix `suggest_imports` for top-level packages** (Issue 20) — When the symbol IS the package name, generate `import {symbol}` not `from {symbol} import {symbol}`.

7. **Fix `get_keyword_help` line indexing** (Issue 21) — Align with 1-indexed lines used by all other tools. Currently requires line-1 workaround.

8. **Investigate `type: ignore` suppression** (Issue 1) — Pyright should respect `# type: ignore` comments. Check `enableTypeIgnoreComments` setting in the LSP initialization params.

9. **Fix `get_context` for decorated functions** (Issue 11) — Jedi reports module scope instead of function scope for `@mcp.tool`-decorated functions. May need to unwrap decorator layers.

10. **Fix `get_symbol_outline` nested function flattening** (Issue 12) — Inner `_work()` closures appear as module-level symbols. Consider filtering or nesting them under their parent method.

11. **Fix `check_layer_violations` scoping** (Issue 15) — Should only scan project source files, not `.venv` or stdlib. Layer matching should use project package paths, not substring matching.

12. **Fix `code_metrics` LOC field** (Issue 14) — The `lines_of_code` field is always 0 while `loc` has correct values. Fix the field mapping.

13. **Respect `__all__` in `find_unused_imports`** (Issue 23) — Skip imports that are listed in the module's `__all__` to avoid false positives on re-export facades.

### P3 — Missing data / validation
14. **Add `files_scanned` to `structural_search` responses** (Issue 22) — Documented but not implemented. Needed to distinguish "no matches" from "scan failure".

15. **Fix `find_unused_imports` validation** (Issue 5) — Make `file_path` optional when `file_paths` is provided.

16. **Add default pagination to `get_symbol_outline`** (Issue 6) — Exclude `.venv` from `root_path` scans. Add a default `limit`.

17. **Warm AutoImport cache on initialization** (Issue 3) — Move `ai.generate_cache()` to `RopeBackend.initialize()`.

18. **Add diagnostic stabilization after `restart_server`** (Issue 13) — Wait for Pyright to finish re-analyzing before returning.

### P4 — Documentation / minor
19. **Document `list_environments` requirements** (Issue 2) — Clarify Jedi environment detection limitations. Confirmed broken on two codebases.

20. **Document `find_errors_static` noise level** (Issue 16) — Note that rope's static analysis has ~80% false positive rate on complex files vs Pyright. Confirmed across two codebases with different failure modes.
