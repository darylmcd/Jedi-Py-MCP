# MCP Server Audit Report

**Server:** python-refactor-mcp v0.2.0
**Backends:** Pyright LSP + Jedi + Rope
**Date:** 2026-03-28
**Tools tested:** 35+ of 75 available

---

## Issue Summary

| Severity | Count |
|---|---|
| Crash / Error | 4 |
| Incorrect Result | 5 |
| Missing Data | 3 |
| Degraded Performance | 1 |
| Cosmetic | 3 |
| **Total** | **19** |

---

## Issue Details

### #1 — `get_symbol_outline`: Output exceeds limits on batch calls
- **Tool:** `get_symbol_outline`
- **Input:** `file_paths` with 5 files
- **Expected:** Manageable JSON output
- **Actual:** 570,315 characters, exceeding client limits
- **Severity:** degraded performance
- **Reproducibility:** always (with >3 files)
- **Recommendation:** Add server-side pagination or truncation; respect `limit` param in batch mode

### #2 — `get_diagnostics`: Duplicate diagnostics at same position
- **Tool:** `get_diagnostics`
- **Input:** `static_errors.py`
- **Expected:** 1 diagnostic at line 22
- **Actual:** 2 identical diagnostics at the same position (same message, same range)
- **Severity:** incorrect result
- **Reproducibility:** always

### #3 — `find_unused_imports`: False positive on `__future__.annotations`
- **Tool:** `find_unused_imports`
- **Input:** `server.py`
- **Expected:** `from __future__ import annotations` NOT flagged (it has runtime effects)
- **Actual:** Flagged as unused
- **Severity:** incorrect result
- **Reproducibility:** always
- **Recommendation:** Whitelist `__future__` imports

### #4 — `get_coupling_metrics`: All zeros for every module
- **Tool:** `get_coupling_metrics`
- **Input:** 7 core modules (server.py, models.py, config.py, errors.py, 3 backends)
- **Expected:** Non-zero Ca/Ce values (server.py imports from 6+ internal modules)
- **Actual:** All metrics returned `afferent_coupling: 0, efferent_coupling: 0, instability: 0`
- **Severity:** incorrect result — tool is non-functional
- **Reproducibility:** always

### #5 — `dead_code_detection`: False positives on decorator-registered functions
- **Tool:** `dead_code_detection`
- **Input:** `root_path` = src/python_refactor_mcp
- **Expected:** Should not flag MCP tool handler functions decorated with `@mcp.tool()`
- **Actual:** Flagged all 75 tool handler functions as dead code ("no references")
- **Severity:** incorrect result — massive false positive rate
- **Reproducibility:** always
- **Recommendation:** Recognize common decorator patterns (`@app.route`, `@mcp.tool`, `@pytest.fixture`) as implicit references

### #6 — `dead_code_detection`: Flags `__all__` as dead code
- **Tool:** `dead_code_detection`
- **Input:** Multiple `__init__.py` files
- **Expected:** `__all__` should never be flagged (Python import system uses it)
- **Actual:** Flagged as "no references" with low confidence
- **Severity:** incorrect result
- **Reproducibility:** always

### #7 — `type_hierarchy`: Returns empty name for classes
- **Tool:** `type_hierarchy`
- **Input:** PyrightLSPClient at pyright_lsp.py:60:6
- **Expected:** `name: "PyrightLSPClient"`, populated supertypes/subtypes
- **Actual:** `name: ""`, empty supertypes and subtypes
- **Severity:** missing data
- **Reproducibility:** always (tested on 2 different classes)

### #8 — `find_references`: Extremely position-sensitive
- **Tool:** `find_references`
- **Input:** PyrightLSPClient — line 60 (docstring) vs line 58 (class keyword)
- **Expected:** Both positions should resolve to the class
- **Actual:** Line 60 returned 0 results; line 58 returned 6 (correct)
- **Severity:** missing data — off-by-2 lines causes total failure with no error
- **Reproducibility:** always
- **Recommendation:** When position lands on a docstring or comment, walk backward to find the owning symbol

### #9 — `call_hierarchy`: Empty results for valid functions
- **Tool:** `call_hierarchy`
- **Input:** pyright_lsp.py:120:14 (method definition)
- **Expected:** Non-empty callers/callees
- **Actual:** Empty result with empty name field
- **Severity:** missing data
- **Reproducibility:** sometimes (position-dependent)

### #10 — `find_references`: Position off-by-2 failure
- **Tool:** `find_references`
- **Input:** Same symbol, line 58 vs line 60
- **Actual:** 0 results at line 60, 6 at line 58
- **Severity:** incorrect result (duplicate of #8 — documenting separately for completeness)

### #11 — `prepare_rename`: Always returns null
- **Tool:** `prepare_rename`
- **Input:** Tested on `severity_to_string` (lsp_converters.py:132:4), `ServerConfig` (config.py:13:8)
- **Expected:** Renameable range and current symbol name
- **Actual:** `{"result": null}` for every position tested
- **Severity:** crash/error — tool appears completely non-functional
- **Reproducibility:** always (tested 5+ positions across 3 files)

### #12 — `prepare_rename`: Systematic failure
- **(Same as #11 — consolidated)**

### #13 — `extract_method`: Generic error message
- **Tool:** `extract_method`
- **Input:** rope_backend.py lines 65-89, method_name="_map_single_operation"
- **Expected:** Either successful preview or descriptive error about why extraction isn't possible
- **Actual:** `"rope extract_method failed for <path>"` — no detail about the cause
- **Severity:** cosmetic (error message unhelpful)
- **Reproducibility:** sometimes (depends on selection)

### #14 — `extract_variable`: Same generic error pattern
- **Tool:** `extract_variable`
- **Input:** rope_backend.py line 64, expression selection
- **Expected:** Descriptive error if extraction isn't possible
- **Actual:** `"rope extract_variable failed for <path>"` — no detail
- **Severity:** cosmetic (error message unhelpful)

### #15 — `change_signature`: Strips type annotations
- **Tool:** `change_signature`
- **Input:** `_build_signature_changers` at rope_backend.py:60:4, operation: `normalize`
- **Expected:** Preserved `operations: list[SignatureOperation]` annotation
- **Actual:** Stripped to bare `operations` (no type annotation)
- **Severity:** incorrect result — data loss on type information
- **Reproducibility:** always
- **Recommendation:** This is likely a rope limitation — the `ArgumentNormalizer` doesn't handle Python 3 type annotations

### #16 — `get_diagnostics`: Stale results after file modification
- **Tool:** `get_diagnostics`
- **Input:** Files modified on disk (jedi_backend.py, static_errors.py)
- **Expected:** Updated diagnostics reflecting the fixes
- **Actual:** Same pre-fix diagnostics returned (stale cache)
- **Severity:** incorrect result
- **Reproducibility:** always after disk edits
- **Root cause:** Pyright LSP client doesn't send `textDocument/didChange` notifications when files are modified externally. The MCP server edits files via rope (direct disk writes), bypassing the LSP open/change protocol.

### #17 — `autoimport_search`: Crashes on common names
- **Tool:** `autoimport_search`
- **Input:** `name="Path"`
- **Expected:** Results like `("Path", "pathlib")`
- **Actual:** `"rope autoimport_search failed for 'Path'"` — crash
- **Severity:** crash/error
- **Reproducibility:** always (for "Path"; may work for other names)
- **Root cause:** Likely AutoImport SQLite cache generation failure or timeout

---

## Tools That Worked Correctly

The following tools performed as expected across all tests:

- `get_module_dependencies` — accurate dependency graph, no false cycles
- `get_workspace_diagnostics` — correct counts (consistent with get_diagnostics)
- `get_syntax_errors` — correctly reported 0 syntax errors
- `find_unused_imports` — correct except for __future__ false positive (#3)
- `code_metrics` — accurate complexity, cognitive, nesting, and LOC metrics
- `find_duplicated_code` — correctly found the 1 real duplicate
- `check_layer_violations` — correctly identified cross-layer imports
- `find_references` — correct when given exact symbol position
- `find_constructors` — accurately found all instantiation sites
- `rename_symbol` — correct preview with proper diff, all references found
- `smart_rename` — produced identical results to rename_symbol
- `organize_imports` — correctly reported "already organized"
- `get_type_coverage` — accurate 100% report
- `get_document_highlights` — correctly identified read/write access
- `goto_definition` — correct navigation to RopeBackend definition
- `get_declaration` — identical to goto_definition (expected for Python)
- `get_type_definition` — correctly resolved `self._config` to `ServerConfig` class
- `deep_type_inference` — traced `self._client` through `_make_client()` to `LSPClient`
- `get_signature_help` — context-aware, resolves nested calls, correct active parameter
- `get_context` — correctly identifies enclosing scope with full qualified name
- `get_type_hint_string` — correct on variable names (empty on string literals is expected)
- `search_symbols` — comprehensive results from both Pyright and Jedi backends
- `get_folding_ranges` — correct structure detection (100 ranges for server.py)
- `structural_search` — correctly blocks unsafe lambda patterns; results appear valid

---

### #18 — `get_semantic_tokens`: Returns empty for valid Python files
- **Tool:** `get_semantic_tokens`
- **Input:** `config.py` with `limit=50`
- **Expected:** Non-zero semantic tokens (namespaces, variables, types, functions, etc.)
- **Actual:** 0 tokens returned
- **Severity:** crash/error — tool appears non-functional
- **Reproducibility:** always (tested on config.py)
- **Root cause:** Pyright LSP server may not have semantic tokens capability enabled in the initialization handshake

### #19 — `structural_search`: No match/no-parse ambiguity
- **Tool:** `structural_search`
- **Input:** `m.ExceptHandler(type=None)`, `m.Call(func=m.Name("print"))`
- **Expected:** "0 matches in N files scanned" or similar feedback
- **Actual:** Empty results with no indication if the pattern was valid but found nothing vs silently failed
- **Severity:** cosmetic — usability gap
- **Reproducibility:** always
- **Recommendation:** Include a `files_scanned` count in the response to distinguish "scanned and found nothing" from "failed to scan"

---

## Recommendations

### High Priority
1. **Fix `prepare_rename`** — completely non-functional; blocks rename workflow validation
2. **Fix `get_coupling_metrics`** — returns all zeros; non-functional
3. **Fix `get_semantic_tokens`** — returns empty; likely needs capability enabled in LSP init
4. **Fix stale diagnostics** (#16) — send `didChange` after rope edits, or force Pyright reload
5. **Fix `autoimport_search` crash** — handle cache generation failures gracefully

### Medium Priority
5. **Reduce `dead_code_detection` false positives** — recognize decorator-based registration patterns and `__all__`
6. **Fix `change_signature` type annotation stripping** — preserve Python 3 annotations during normalization
7. **Fix duplicate diagnostics** (#2) — deduplicate before returning
8. **Whitelist `__future__` in `find_unused_imports`**

### Low Priority
9. **Improve `find_references` position tolerance** — snap to nearest symbol when landing on docstring/whitespace
10. **Improve rope error messages** — include the underlying exception message, not just the file path
11. **Add pagination to `get_symbol_outline`** for large batch requests
12. **Populate `name` field in `type_hierarchy` results**
