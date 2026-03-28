# Comprehensive Best Practices Analysis

**Date:** 2026-03-27
**Scope:** All 37 MCP tools exposed by the Python Refactor MCP server, plus backends, utilities, and architecture.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Assessment](#architecture-assessment)
3. [Tool-by-Tool Analysis](#tool-by-tool-analysis)
   - [Analysis Tools (12)](#analysis-tools)
   - [Navigation Tools (9)](#navigation-tools)
   - [Refactoring Tools (16)](#refactoring-tools)
   - [Search Tools (5)](#search-tools)
   - [Composite Tools (2)](#composite-tools)
4. [Backend Analysis](#backend-analysis)
5. [Utility Module Analysis](#utility-module-analysis)
6. [Cross-Cutting Concerns](#cross-cutting-concerns)
7. [Prioritized Recommendations](#prioritized-recommendations)

---

## Executive Summary

The MCP server is well-architected with strong separation of concerns, protocol-based decoupling, and consistent patterns. Key strengths include the multi-backend fallback strategy (Pyright primary, Jedi fallback), atomic file writes, deterministic output ordering, and proper error boundary handling. The main improvement areas are: missing workspace path validation on tool inputs, lack of request-level timeouts on some operations, and absence of concurrency guards on certain workspace-wide scans.

**Overall Grade: B+** — Production-quality foundations with specific hardening gaps.

---

## Architecture Assessment

### Strengths

| Area | Implementation | Best Practice Alignment |
|------|---------------|------------------------|
| **Layered Architecture** | `server.py` → `tools/` → `backends/` | Excellent. Clean separation between MCP registration, orchestration logic, and backend I/O. |
| **Protocol-Based Decoupling** | Each tool module defines `Protocol` classes for its backends | Excellent. Enables testing with mocks and prevents tight coupling. Tools never import backend classes directly. |
| **Error Hierarchy** | `BackendError` → `PyrightError` / `RopeError` / `JediError` / `ConfigError` | Good. Clear error taxonomy. The `_tool_error_boundary` decorator converts all `BackendError` to `ValueError` for MCP consumers. |
| **Tool Annotations** | `_READONLY` and `_DESTRUCTIVE` tool annotations | Excellent. MCP-compliant annotations help clients understand tool capabilities. |
| **Lifespan Management** | `app_lifespan` context manager creates/disposes backends | Good. Pyright gets `shutdown()`, Rope gets `close()`. Jedi has no cleanup (intentional — stateless). |
| **Pydantic Models** | All inputs/outputs use typed Pydantic models | Excellent. Provides validation, serialization, and documentation in one layer. |

### Weaknesses

| Area | Issue | Severity |
|------|-------|----------|
| **Global Mutable State** | `_workspace_root` module-level global mutated by `run_server()` | Medium. Not thread-safe. Single-server assumption is fine for stdio transport but fragile. |
| **No Workspace Path Validation at Tool Layer** | Tools accept raw `file_path: str` without validating it's within the workspace | High. `validate_workspace_path()` exists in `util/shared.py` but is never called by any tool. Files outside the workspace could be read/modified. |
| **Missing Request Timeouts** | Rope operations run via `asyncio.to_thread()` with no timeout | Medium. A pathological rope refactoring could block indefinitely. |
| **No Rate Limiting / Concurrency Control** | Workspace-wide scans (dead_code, workspace_diagnostics, structural_search) can be expensive | Low-Medium. Multiple concurrent calls could overwhelm the system. |

---

## Tool-by-Tool Analysis

### Analysis Tools

#### 1. `find_references`
- **Backend:** Pyright primary, Jedi fallback with merge
- **Strengths:** Deduplication via `location_key`, truncation support, source attribution ("pyright"/"jedi"/"combined")
- **Best Practice Alignment:** Good. Multi-backend merge with sorted, deduplicated results.
- **Issues:**
  - Bare `except Exception` on Jedi fallback swallows all errors silently. Should log at DEBUG level.
  - Context line attachment reads entire files into memory per unique path (cached within call, but no global cache).

#### 2. `get_type_info`
- **Backend:** Pyright primary, Jedi fallback
- **Strengths:** `_is_unknown_type` heuristic correctly detects useless Pyright responses and falls back.
- **Best Practice Alignment:** Good. Graceful degradation pattern.
- **Issues:** None significant.

#### 3. `get_hover_info`
- **Backend:** Delegates entirely to `get_type_info`
- **Best Practice Alignment:** Good. Alias tool for different semantic intent.
- **Issues:** Could be merged with `get_type_info` to reduce tool surface area, but separation is defensible for client ergonomics.

#### 4. `get_completions`
- **Backend:** Pyright only
- **Strengths:** Sorted output, limit support.
- **Issues:** No Jedi fallback. For dynamic code where Pyright may return empty results, Jedi completions could supplement.

#### 5. `get_documentation`
- **Backend:** Jedi only
- **Strengths:** Direct delegation with clean model return.
- **Issues:** No Pyright fallback for documentation. Pyright hover contains markdown docs that could be used.

#### 6. `get_signature_help`
- **Backend:** Pyright only
- **Strengths:** Clean, focused tool.
- **Issues:** No fallback. The separate `get_call_signatures_fallback` tool exists for Jedi — this split forces the client to try two tools instead of the server handling fallback internally.

#### 7. `get_call_signatures_fallback`
- **Backend:** Jedi only
- **Best Practice Alignment:** Acceptable as a separate tool, but ideally the server would handle fallback automatically within `get_signature_help`.
- **Issues:** Client must know to try this after `get_signature_help` returns None.

#### 8. `get_document_highlights`
- **Backend:** Pyright only
- **Strengths:** Sorted by position and kind.
- **Issues:** None significant.

#### 9. `get_inlay_hints`
- **Backend:** Pyright only
- **Strengths:** Defaults to full file when `end_line` is omitted (reads file to determine line count).
- **Issues:** Reading the full file just to count lines is wasteful for large files. Could use `Path.stat()` approximation or lazy streaming.

#### 10. `get_semantic_tokens`
- **Backend:** Pyright only
- **Strengths:** Sorted by position.
- **Issues:** Can return very large payloads for big files with no limit parameter.

#### 11. `get_diagnostics`
- **Backend:** Pyright only
- **Strengths:** Severity filtering with validation, limit support, deterministic sort.
- **Best Practice Alignment:** Good. Input validation on `severity_filter` with clear error message.
- **Issues:** None significant.

#### 12. `get_workspace_diagnostics`
- **Backend:** Pyright (iterated per file)
- **Strengths:** Aggregated counts per file, sorted output.
- **Issues:**
  - **Performance:** Iterates all Python files sequentially, calling `get_diagnostics()` per file. No concurrency. For large workspaces this is O(n) sequential LSP requests.
  - **Missing limit parameter.**

---

### Navigation Tools

#### 13. `call_hierarchy`
- **Backend:** Pyright only
- **Strengths:** BFS traversal with depth control, max_items cap, deduplication, decorator detection with AST-based retry.
- **Best Practice Alignment:** Excellent. Sophisticated decorator heuristic to handle cursor-on-decorator edge case.
- **Issues:**
  - The decorator detection reads and parses the file with `ast.parse` — correct but adds latency.
  - Depth validation (`depth < 1` raises) is good.
  - Direction validation is thorough.

#### 14. `type_hierarchy`
- **Backend:** Pyright only
- **Strengths:** Direction aliases for backward compat, AST-resolved class position retry, BFS traversal.
- **Best Practice Alignment:** Good. `_resolve_class_position` handles cursor-on-`class`-keyword.
- **Issues:** Code duplication with `_traverse_calls` / `_traverse_types` — these are structurally identical. Could be a single generic function.

#### 15. `goto_definition`
- **Backend:** Pyright primary, Jedi fallback
- **Strengths:** Deduplication, sorted output, fallback.
- **Issues:** Bare `except Exception` on Jedi fallback. Should log.

#### 16. `get_symbol_outline`
- **Backend:** Pyright (iterated per file for workspace)
- **Strengths:** Recursive filter collection, regex name pattern with compile-time validation, kind filter.
- **Issues:**
  - **Performance:** Sequential file iteration for workspace-wide outlines with no concurrency.
  - Regex pattern injection is mitigated by wrapping in `re.compile` with error handling — good.

#### 17. `selection_range`
- **Backend:** Pyright only
- **Strengths:** Input validation (empty positions list).
- **Issues:** None significant.

#### 18. `find_implementations`
- **Backend:** Pyright only
- **Strengths:** Deduplication, sorted output.
- **Issues:** None significant.

#### 19. `get_declaration`
- **Backend:** Pyright only
- **Issues:** None significant.

#### 20. `get_type_definition`
- **Backend:** Pyright only
- **Issues:** None significant.

#### 21. `get_folding_ranges`
- **Backend:** Pyright primary, AST fallback
- **Strengths:** `_ast_folding_ranges` provides a robust fallback with import grouping detection.
- **Best Practice Alignment:** Excellent fallback strategy.
- **Issues:** None significant.

---

### Refactoring Tools

#### 22. `rename_symbol`
- **Backend:** Pyright validation + Rope execution
- **Strengths:** `_ensure_renameable` runs Pyright preflight before rope rename. Post-apply diagnostics attached.
- **Best Practice Alignment:** Excellent. Preflight → execute → validate pattern.
- **Issues:** None significant.

#### 23. `extract_method`
- **Backend:** Rope execution + Pyright post-validation
- **Strengths:** `similar` parameter for replacing similar code fragments.
- **Issues:** No pre-validation that the selection range is valid Python.

#### 24. `extract_variable`
- **Backend:** Rope execution + Pyright post-validation
- **Issues:** Same as extract_method — no selection validation.

#### 25. `inline_variable`
- **Backend:** Rope execution + Pyright post-validation
- **Issues:** None significant.

#### 26. `move_symbol`
- **Backend:** Rope execution + Pyright post-validation
- **Issues:**
  - No validation that `destination_file` exists or is a Python file.
  - No workspace boundary check on `destination_file`.

#### 27. `apply_code_action`
- **Backend:** Pyright only
- **Strengths:** Title-based action selection with exact and substring matching, deduplication of text edits.
- **Best Practice Alignment:** Good. `_workspace_edit_to_text_edits` handles both `changes` and `documentChanges` LSP formats.
- **Issues:** None significant.

#### 28. `organize_imports`
- **Backend:** Pyright only
- **Strengths:** Graceful "already organized" result when no actions available.
- **Issues:** None significant.

#### 29. `prepare_rename`
- **Backend:** Pyright only
- **Issues:** None — correctly read-only.

#### 30. `introduce_parameter`
- **Backend:** Rope execution + Pyright post-validation
- **Issues:** No validation on `parameter_name` (could be a Python keyword or invalid identifier).

#### 31. `encapsulate_field`
- **Backend:** Rope execution + Pyright post-validation
- **Issues:** None significant.

#### 32. `change_signature`
- **Backend:** Rope execution + Pyright post-validation
- **Strengths:** Uses `_ensure_renameable` for preflight.
- **Issues:**
  - `SignatureOperation.op` is a free-form string. No validation that the op value is one of the supported operations before passing to rope.

#### 33. `restructure`
- **Backend:** Rope execution + Pyright post-validation
- **Issues:** Pattern/goal strings are passed directly to rope's `Restructure`. Rope does its own parsing, but error messages may be cryptic.

#### 34. `use_function`
- **Backend:** Rope execution + Pyright post-validation
- **Issues:** None significant.

#### 35. `introduce_factory`
- **Backend:** Rope execution + Pyright post-validation
- **Issues:** No validation on `factory_name` being a valid Python identifier.

#### 36. `module_to_package`
- **Backend:** Rope execution + Pyright post-validation
- **Issues:** None significant.

#### 37. `local_to_field` / `method_object`
- **Backend:** Rope execution + Pyright post-validation
- **Issues:** None significant.

---

### Search Tools

#### 38. `find_constructors`
- **Backend:** Pyright references + AST analysis
- **Strengths:** Cross-references Pyright references with AST call nodes to identify true constructor calls. Deduplication.
- **Issues:**
  - **Performance:** Reads and parses every file containing references with `ast.parse`. For large projects with many references, this could be slow.
  - No error handling on `path.read_text()` for referenced files.

#### 39. `search_symbols`
- **Backend:** Pyright + Jedi merged
- **Strengths:** Dual-backend merge with deduplication. Pyright results take priority.
- **Issues:** Bare `except Exception` on both backends. If both fail silently, returns empty with no indication of error.

#### 40. `structural_search`
- **Backend:** LibCST with `asyncio.gather` concurrency
- **Strengths:**
  - **Security:** AST-validates the pattern before `eval()`. Only allows `m`, `cst`, `True`, `False`, `None` as top-level names. `__builtins__` set to `{}`.
  - **Performance:** Uses `asyncio.to_thread` per file with `asyncio.gather` for concurrency.
  - Helpful error message with examples on invalid patterns.
- **Best Practice Alignment:** Excellent security mitigation for `eval()`. The AST pre-validation prevents attribute-chain sandbox escapes.
- **Issues:**
  - `return_exceptions=True` means parse errors in individual files are silently swallowed (they become Exception objects filtered by `isinstance(result, list)`). Should log these.

#### 41. `dead_code_detection`
- **Backend:** Pyright diagnostics + reference counting
- **Strengths:** Dual strategy: diagnostic-based detection (unused/not-accessed tags) + reference-count-based detection (module-level symbols with no external refs). Exclude patterns with regex.
- **Issues:**
  - **Performance:** Calls `get_references()` for every module-level symbol in every target file. O(symbols * files) LSP requests. Very expensive for large workspaces.
  - `compiled_excludes` regex patterns are not validated for compile errors.
  - Only scans module-level symbols, not class methods or nested functions. This is documented behavior but worth noting.

#### 42. `suggest_imports`
- **Backend:** Pyright code actions + Jedi name search
- **Strengths:** Combines Pyright quick-fix import suggestions with Jedi's name search. Deduplication by (symbol, module).
- **Issues:** None significant.

---

### Composite Tools

#### 43. `smart_rename`
- **Backend:** Pyright preflight + Rope rename
- **Strengths:** Duplicates the `_ensure_renameable` logic from refactoring.py for a self-contained composite tool.
- **Issues:**
  - **Code duplication:** The preflight logic in `smart_rename` is copy-pasted from `refactoring._ensure_renameable`. Should share the implementation.
  - Difference from `rename_symbol`: `smart_rename` does NOT call `_ensure_renameable` — it inlines the logic. This means divergence if one is updated without the other.

#### 44. `diff_preview`
- **Backend:** Pure utility (no backend needed)
- **Strengths:** Groups edits by file, produces unified diffs.
- **Issues:** None significant.

---

## Backend Analysis

### Pyright LSP Client (`pyright_lsp.py`)

| Area | Assessment |
|------|-----------|
| **Subprocess Management** | Good. Candidate command fallback strategy with multiple launch attempts. Graceful shutdown with terminate/kill escalation. |
| **Request Timeout** | Good. Configurable via `PYRIGHT_REQUEST_TIMEOUT_SECONDS` env var (default 5s). |
| **File Tracking** | Good. `ensure_file_open` + `notify_file_changed` with version tracking. |
| **Diagnostic Caching** | Good. `_handle_publish_diagnostics` caches pushed diagnostics with event signaling. |
| **Error Handling** | Good. `_is_unhandled_method_error` gracefully handles unsupported LSP methods. |
| **Issue: Startup Timeout** | The `initialize` request has a 15s timeout but individual candidate attempts don't have early-exit on connection failure. Could spend 15s * N candidates on startup. |
| **Issue: No Health Check** | No mechanism to detect if Pyright process crashes after startup. The reader loop fails pending requests, but no automatic restart. |

### Rope Backend (`rope_backend.py`)

| Area | Assessment |
|------|-----------|
| **Thread Safety** | Good. All rope operations run via `asyncio.to_thread()` to avoid blocking the event loop. |
| **Rollback on Failure** | Excellent. `_apply_edits` captures originals and rolls back on any write failure. |
| **Atomic Writes** | Uses `write_atomic` from diff.py — temp file + `os.replace`. |
| **Project Validation** | Calls `project.validate(project.root)` before each operation — ensures rope's internal state is fresh. |
| **Issue: Broad Exception Wrapping** | Every operation catches `Exception` and re-raises as `RopeError`. Original stack trace is preserved via `from exc`, but the outer message is generic (e.g., "rope rename failed for X:Y:Z"). |
| **Issue: No Timeout** | `asyncio.to_thread()` calls have no timeout wrapper. A rope operation analyzing a massive codebase could block indefinitely. |

### LSP Client (`lsp_client.py`)

| Area | Assessment |
|------|-----------|
| **JSON-RPC Compliance** | Good. Proper id generation, notification vs request handling, server-initiated request responses. |
| **Write Lock** | Good. `_write_lock` prevents interleaved writes to subprocess stdin. |
| **Shutdown Sequence** | Excellent. shutdown request → exit notification → stdin close → wait with terminate/kill escalation. Pending futures failed on shutdown. |
| **Stderr Draining** | Good. Prevents child process from blocking on full stderr buffers. |
| **Issue: No Reconnection** | If the LSP process dies, all pending requests fail but there's no auto-restart mechanism. |

---

## Utility Module Analysis

### `diff.py`
- **Atomic Writes:** Excellent. `write_atomic` uses `tempfile.mkstemp` + `os.replace` with cleanup on failure.
- **Edit Application:** `apply_text_edits` sorts edits in reverse order and applies from bottom to top — correct approach to avoid offset invalidation.
- **Overlap Detection:** Validates that edits don't overlap — good safety check.

### `paths.py`
- **URI Handling:** Handles Windows drive letter edge cases correctly (leading `/` stripping, forward-to-back slash conversion).
- **Normalization:** `normalize_path` uses `os.path.abspath` (not `resolve()`) to avoid symlink issues — deliberately documented.

### `file_filter.py`
- **Directory Exclusion:** Comprehensive default exclusion set (`.venv`, `node_modules`, `__pycache__`, etc.).
- **Performance:** Uses `os.walk` with in-place pruning — efficient for large trees.
- **Issue:** `.pyi` stub files are excluded (only `.py` matched). This is likely intentional but means stub-only packages are invisible.

### `shared.py`
- **`validate_workspace_path`:** EXISTS but is NEVER CALLED by any tool. This is the most significant security gap.
- **`apply_limit`:** Clean implementation with validation (`limit < 1` raises).
- **`attach_post_apply_diagnostics`:** Used by all refactoring tools. Notifies Pyright of changes and collects fresh diagnostics.

### `config.py`
- **Python Detection:** Thorough cascade: `.venv`/`venv` → `pyproject.toml` poetry config → `$VIRTUAL_ENV` → `python3` → `python`.
- **Issue:** No caching of config discovery. Called once at startup via `app_lifespan`, so this is fine.

---

## Cross-Cutting Concerns

### 1. Security: Path Traversal (HIGH)

**Problem:** `validate_workspace_path()` exists in `util/shared.py` but is never called. Every tool that accepts `file_path`, `source_file`, or `destination_file` passes the raw string directly to backends. A malicious client could:
- Read files outside the workspace (e.g., `/etc/passwd`, `~/.ssh/id_rsa`)
- Modify files outside the workspace via refactoring tools with `apply=True`

**Recommendation:** Add workspace path validation in `_tool_error_boundary` or at the server.py tool registration layer. Validate all `file_path` parameters before delegation.

### 2. Silent Error Swallowing (MEDIUM)

**Problem:** Multiple locations use bare `except Exception: pass` or `except Exception: return []`:
- `analysis.py:173` — Jedi fallback in `find_references`
- `analysis.py:251` — Jedi fallback in `get_type_info`
- `navigation.py:396` — Jedi fallback in `goto_definition`
- `search.py:393-401` — Both backends in `search_symbols`

**Recommendation:** Add `logging.debug("backend fallback failed", exc_info=True)` to all catch blocks. This preserves the graceful degradation behavior while making debugging possible.

### 3. Performance: Sequential Workspace Scans (MEDIUM)

**Problem:** Several tools iterate all workspace files sequentially:
- `get_workspace_diagnostics` — one `get_diagnostics()` call per file
- `get_symbol_outline` (workspace mode) — one `get_document_symbols()` call per file
- `dead_code_detection` — one `get_references()` call per symbol per file

**Recommendation:** Use `asyncio.gather` with bounded concurrency (e.g., `asyncio.Semaphore(10)`) for workspace-wide operations. `structural_search` already does this correctly with `asyncio.gather`.

### 4. Missing Input Validation (MEDIUM)

Several tools accept string parameters that should be validated:
- `introduce_parameter`: `parameter_name` should be a valid Python identifier
- `introduce_factory`: `factory_name` should be a valid Python identifier
- `change_signature`: `SignatureOperation.op` should be validated against known operations
- `extract_method`: `method_name` should be a valid Python identifier
- `extract_variable`: `variable_name` should be a valid Python identifier

**Recommendation:** Add `str.isidentifier()` checks for all name parameters. Add an `op` enum or validation set for `SignatureOperation`.

### 5. Code Duplication (LOW)

- `_traverse_calls` and `_traverse_types` in `navigation.py` are structurally identical BFS traversals parameterized only by type. Could be a single generic function.
- `_end_position_for_content` is duplicated in `refactoring.py` and `rope_backend.py`.
- Preflight rename validation is duplicated between `refactoring._ensure_renameable` and `composite.smart_rename`.

### 6. Missing Tool: Workspace Symbol Workspace Diagnostics Summary (LOW)

The `get_workspace_diagnostics` tool iterates files but doesn't offer a simple "total errors in workspace" counter. Adding a summary mode would reduce token overhead for LLM clients.

---

## Prioritized Recommendations

### P0 — Security

1. **Enforce workspace path validation** on all tool `file_path` inputs. Add a decorator or validation step in `server.py` that calls `validate_workspace_path()` before any tool execution.

### P1 — Reliability

2. **Add logging to silent exception handlers.** Replace bare `except Exception: pass` with logged fallbacks across all tool modules.
3. **Add timeouts to rope operations.** Wrap `asyncio.to_thread()` calls with `asyncio.wait_for()` using a configurable timeout (default 30s).
4. **Validate identifier name parameters.** Add `str.isidentifier()` checks for `method_name`, `variable_name`, `parameter_name`, `factory_name`.

### P2 — Performance

5. **Parallelize workspace-wide scans.** Use `asyncio.gather` with a semaphore for `get_workspace_diagnostics`, `get_symbol_outline` (workspace mode), and `dead_code_detection`.
6. **Add limit parameter to `get_semantic_tokens`** and `get_workspace_diagnostics` to prevent unbounded responses.

### P3 — Code Quality

7. **Deduplicate `_traverse_calls`/`_traverse_types`** into a single generic BFS function.
8. **Deduplicate `_end_position_for_content`** — move to `util/shared.py`.
9. **Unify rename preflight logic** between `refactoring._ensure_renameable` and `composite.smart_rename`.
10. **Consider merging `get_signature_help` and `get_call_signatures_fallback`** into a single tool with automatic Jedi fallback.

### P4 — Observability

11. **Add structured logging** to all tool functions (not just `ctx.debug`). Include timing information for backend calls.
12. **Expose backend health** as a tool or resource (Pyright process status, rope project state).
