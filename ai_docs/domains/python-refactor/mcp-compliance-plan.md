# MCP Best Practices Compliance Analysis & Implementation Plan

**Date:** 2026-03-28
**Reference:** `ai_docs/mcp_best_practices.md`
**Scope:** Full analysis of `python-refactor-mcp` server against industry best practices

---

## Compliance Summary

| Best Practice Area | Grade | Status |
|--------------------|-------|--------|
| 1. Design Principles | A | Compliant |
| 2. Server Architecture | A | Compliant |
| 3. Tool Design | C+ | Gaps: descriptions, tool count, response design |
| 4. Tool Annotations | B | Gaps: missing `idempotentHint`, `title`, additive annotation |
| 5. Input Validation | A- | Compliant (workspace paths, identifiers, SignatureOp validated) |
| 6. Error Handling | B+ | Gap: Jedi fallback silent swallowing in tool modules |
| 7. Security | A- | Compliant (path traversal fixed, eval sandboxed) |
| 8. Auth & Authorization | N/A | stdio-only server, auth not applicable |
| 9. Transport | A | Compliant (stdio, correct stdout discipline) |
| 10. Resource Management | N/A | No MCP resources exposed (acceptable for tool-only server) |
| 11. Prompt Design | N/A | No MCP prompts exposed (acceptable) |
| 12. Sampling | N/A | Not applicable |
| 13. Performance | C | Gaps: no concurrency on workspace scans, Jedi no timeouts, no rate limiting |
| 14. Logging & Observability | C+ | Gaps: no structured logging, no timing, no logging capability |
| 15. Lifecycle Management | B+ | Compliant (lifespan, health check, auto-restart) |
| 16. Testing | B | Gap: no contract tests, no load tests |
| 17. Deployment | B | Compliant (PyInstaller, manifest.json) |
| 18. SDK Patterns | A | Compliant (FastMCP, async, lifespan, Pydantic) |
| 19. Anti-Patterns | B+ | Minor: tool count high, some code duplication |

**Overall: B+ — Strong foundations with specific gaps in tool design, performance, and observability.**

---

## Detailed Gap Analysis

### GAP-01: Tool Descriptions Are Technical-Only (HIGH impact)

**Best Practice (Section 3):** "Write descriptions explaining when and how to use tools within larger workflows, not just technical details. Tool descriptions have a greater impact than model choice on quality."

**Current State:** All 45 tool docstrings are one-line technical descriptions:
- `"Find symbol references for the provided source location."`
- `"Get type information for the provided source location."`
- `"Extract selected code into a new method."`

**Impact:** LLMs cannot effectively determine which tool to use or when. No workflow context, no use-case examples, no operational notes.

**Fix:** Rewrite all 45 tool docstrings to include: what it does, when to use it, key parameters, and relationship to other tools. Use structured format.

**Files:** `server.py`

---

### GAP-02: Tool Count Exceeds LLM Reliability Threshold (MEDIUM impact)

**Best Practice (Section 3):** "LLMs become unreliable when exposed to more than 30-40 tools. Consider progressive discovery or semantic search patterns."

**Current State:** 45 registered tools. Some overlap:
- `get_type_info` / `get_hover_info` (alias)
- `get_signature_help` / `get_call_signatures_fallback` (should be single tool with internal fallback)
- `rename_symbol` / `smart_rename` (overlapping functionality)

**Impact:** Moderate — LLM tool selection degrades beyond 30-40 tools.

**Fix:**
1. Merge `get_signature_help` + `get_call_signatures_fallback` into single tool with internal Jedi fallback (already in backlog)
2. Consider merging `get_type_info` / `get_hover_info` (same underlying call)
3. Consider merging `rename_symbol` / `smart_rename`
4. Target: reduce to ~40 tools

**Files:** `server.py`, `tools/analysis/type_info.py`

---

### GAP-03: Missing `idempotentHint` Annotations (MEDIUM impact)

**Best Practice (Section 4):** "`idempotentHint`: Safe to call repeatedly with same arguments."

**Current State:** Only two annotation variants defined:
- `_READONLY` — `readOnlyHint=True, destructiveHint=False, openWorldHint=False`
- `_DESTRUCTIVE` — `readOnlyHint=False, destructiveHint=True, openWorldHint=False`

All read-only tools are idempotent but not annotated as such. Refactoring tools with `apply=False` (preview mode) are also effectively read-only and idempotent.

**Fix:**
1. Add `idempotentHint=True` to `_READONLY` annotation
2. Create `_ADDITIVE` annotation for refactoring tools that are additive, not destructive (e.g., `organize_imports`, `apply_code_action` with certain actions)
3. Add `title` field to all tool annotations for human-readable display

**Files:** `server.py`

---

### GAP-04: Jedi Backend Missing Timeouts (HIGH impact)

**Best Practice (Section 13):** "SHOULD establish timeouts for all sent requests."

**Current State:** All 7 `asyncio.to_thread()` calls in `jedi_backend.py` have NO timeout wrapper. Rope backend correctly uses `asyncio.wait_for()` with configurable timeout.

**Affected methods:**
- `get_references()` — line 121
- `goto_definition()` — line 141
- `infer_type()` — line 171
- `search_names()` — line 209
- `search_symbols()` — line 258
- `get_signatures()` — line 303
- `get_help()` — line 367

**Fix:** Mirror the rope pattern — add configurable timeout via `JEDI_OPERATION_TIMEOUT_SECONDS` env var (default 10s). Wrap all `asyncio.to_thread()` calls with `asyncio.wait_for()`.

**Files:** `backends/jedi_backend.py`

---

### GAP-05: Sequential Workspace-Wide Scans (MEDIUM impact)

**Best Practice (Section 13):** "Use concurrent execution for workspace-wide operations. Avoid sequential iteration over all workspace files."

**Current State:** These tools iterate all workspace files sequentially:
- `get_workspace_diagnostics` — one `get_diagnostics()` call per file
- `get_symbol_outline` (workspace mode) — one `get_document_symbols()` call per file
- `dead_code_detection` — one `get_references()` call per symbol per file

`structural_search` already uses `asyncio.gather` correctly.

**Fix:** Apply bounded concurrency (`asyncio.Semaphore(10)` + `asyncio.gather`) to all workspace-wide operations. Already tracked in backlog.

**Files:** `tools/analysis/diagnostics.py`, `tools/navigation/outline.py`, `tools/search/dead_code.py`

---

### GAP-06: No Structured Logging or Timing (MEDIUM impact)

**Best Practice (Section 14):** "Use structured JSON logs with correlation IDs. Include performance metrics (operation timing, resource usage)."

**Current State:**
- `server.py` uses `ctx.debug()` for 45 tool calls (good baseline)
- Backend modules use Python `logging` (`_LOGGER.debug(...)`)
- No timing information on any operation
- No correlation IDs
- No `logging` capability declared on the MCP server
- No structured format

**Fix:**
1. Add timing to all tool functions (measure elapsed time, log via `ctx.debug`)
2. Add `logging` capability to FastMCP server declaration
3. Upgrade backend logging to include timing for LSP/rope/Jedi calls
4. Add structured context (file_path, tool_name) to log messages

**Files:** `server.py`, all backend modules

---

### GAP-07: Silent Error Swallowing in Tool-Level Fallbacks (LOW-MEDIUM impact)

**Best Practice (Section 6):** "Never use bare `except Exception: pass` — always log at minimum DEBUG level."

**Current State:** The Jedi backend properly re-raises as `JediError`. However, the tool-level fallback patterns in the orchestration layer may still catch and silence these. Need to verify each fallback handler logs before swallowing.

Specific concern areas (from explore agent):
- `tools/analysis/references.py` — Jedi fallback in find_references
- `tools/analysis/type_info.py` — Jedi fallback in get_type_info
- `tools/navigation/definitions.py` — Jedi fallback in goto_definition
- `tools/search/symbols.py` — Both backends in search_symbols

**Fix:** Audit all tool-level fallback `except` blocks. Add `_LOGGER.debug("backend fallback failed", exc_info=True)` to any that swallow silently.

**Files:** `tools/analysis/references.py`, `tools/analysis/type_info.py`, `tools/navigation/definitions.py`, `tools/search/symbols.py`

---

### GAP-08: No Rate Limiting or Concurrency Control (LOW impact)

**Best Practice (Section 7, 13):** "MUST rate limit tool invocations. Implement concurrency guards on expensive workspace-wide scans."

**Current State:** No rate limiting, no semaphores, no concurrency guards.

**Impact:** Low for stdio (single client), but a malicious or buggy client could fire many concurrent workspace-wide scans.

**Fix:** Add an `asyncio.Semaphore` to workspace-wide operations (`get_workspace_diagnostics`, `dead_code_detection`, workspace `get_symbol_outline`, `structural_search`) to prevent resource exhaustion. Rate limiting is less critical for stdio transport.

**Files:** `server.py` or shared utility

---

### GAP-09: No Server Description/Instructions (MEDIUM impact)

**Best Practice (Section 3, community):** "Provide a rich description of the MCP server to clearly explain its purpose, capabilities, and how tools should be mapped to workflows."

**Current State:** `FastMCP("Python Refactor", lifespan=app_lifespan)` — name only, no description, no version, no instructions.

**Fix:** Add `description`, `version`, and `instructions` parameters to the FastMCP constructor to help LLM clients understand the server's purpose and tool organization.

**Files:** `server.py`

---

### GAP-10: Missing `limit` on Large-Payload Tools (LOW impact)

**Best Practice (Section 13):** "Implement `limit` parameters on tools that can return large result sets."

**Current State:** `get_semantic_tokens` has no `limit` parameter and can return very large payloads for big files.

**Fix:** Add `limit: int | None = None` parameter to `get_semantic_tokens`. Already tracked in backlog.

**Files:** `tools/analysis/tokens.py`, `server.py`

---

### GAP-11: No Contract Tests (LOW impact)

**Best Practice (Section 16):** "Contract tests: MCP protocol compliance verification."

**Current State:** Unit tests + integration tests exist. No tests verifying MCP protocol compliance (correct JSON-RPC responses, capability negotiation, tool listing).

**Fix:** Add contract tests using FastMCP in-memory transport to verify:
- Server initializes with correct capabilities
- Tool list matches expected count and names
- Tool calls return correct Pydantic model shapes
- Error boundary produces correct `isError` responses

**Files:** `tests/contract/` (new)

---

### GAP-12: Code Duplication (LOW impact)

**Best Practice (Section 19):** "Mixed responsibilities: business logic coupled with MCP infrastructure."

**Current State:**
- `_traverse_calls` / `_traverse_types` in navigation are structurally identical BFS
- `_end_position_for_content` duplicated in refactoring + rope_backend
- Rename preflight duplicated between refactoring and composite

**Fix:** Already tracked in backlog. Unify traversals, share helpers, share preflight logic.

**Files:** `tools/navigation/hierarchy.py`, `tools/refactoring/rename.py`, `tools/composite.py`, `util/shared.py`

---

## Implementation Plan

### Phase 1: Critical Compliance (Security + Reliability)

**Priority: HIGH | Effort: Small | Impact: Prevents failures and data loss**

| # | Task | Files | Est. |
|---|------|-------|------|
| 1.1 | Add timeouts to all 7 Jedi `asyncio.to_thread()` calls via `asyncio.wait_for()` with `JEDI_OPERATION_TIMEOUT_SECONDS` env var (default 10s) | `backends/jedi_backend.py` | 30min |
| 1.2 | Audit and fix silent error swallowing in tool-level fallback handlers — add `_LOGGER.debug(..., exc_info=True)` to all bare `except` blocks | `tools/analysis/references.py`, `tools/analysis/type_info.py`, `tools/navigation/definitions.py`, `tools/search/symbols.py` | 30min |
| 1.3 | Add concurrency semaphore for workspace-wide scans (shared `_WORKSPACE_SCAN_SEMAPHORE = asyncio.Semaphore(2)`) | `server.py` or `util/shared.py` | 15min |

---

### Phase 2: Tool Quality (Descriptions + Annotations)

**Priority: HIGH | Effort: Medium | Impact: Dramatically improves LLM tool selection accuracy**

| # | Task | Files | Est. |
|---|------|-------|------|
| 2.1 | Rewrite all 45 tool docstrings with workflow-oriented descriptions: what, when, key params, related tools | `server.py` | 2hr |
| 2.2 | Add `idempotentHint=True` to `_READONLY` annotation | `server.py` | 5min |
| 2.3 | Create `_ADDITIVE` annotation: `readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False` for non-destructive mutations (organize_imports, apply_code_action) | `server.py` | 15min |
| 2.4 | Add server description, version, and instructions to `FastMCP()` constructor | `server.py` | 30min |
| 2.5 | Merge `get_signature_help` + `get_call_signatures_fallback` into single tool with internal Jedi fallback | `tools/analysis/completions.py`, `server.py` | 45min |

---

### Phase 3: Performance (Concurrency + Output Limits)

**Priority: MEDIUM | Effort: Medium | Impact: Prevents timeouts on large workspaces**

| # | Task | Files | Est. |
|---|------|-------|------|
| 3.1 | Parallelize `get_workspace_diagnostics` with bounded `asyncio.gather` + `Semaphore(10)` | `tools/analysis/diagnostics.py` | 45min |
| 3.2 | Parallelize workspace-mode `get_symbol_outline` with same pattern | `tools/navigation/outline.py` | 45min |
| 3.3 | Parallelize `dead_code_detection` reference counting with bounded concurrency | `tools/search/dead_code.py` | 45min |
| 3.4 | Add `limit` parameter to `get_semantic_tokens` | `tools/analysis/tokens.py`, `server.py` | 15min |

---

### Phase 4: Observability (Logging + Timing)

**Priority: MEDIUM | Effort: Medium | Impact: Enables debugging and performance analysis**

| # | Task | Files | Est. |
|---|------|-------|------|
| 4.1 | Add timing measurement to all tool functions — log elapsed ms via `ctx.debug` | `server.py` | 1hr |
| 4.2 | Add timing to backend calls (Pyright request, Jedi thread, Rope operation) | All backend modules | 1hr |
| 4.3 | Declare `logging` capability on FastMCP server if supported by SDK version | `server.py` | 15min |

---

### Phase 5: Code Quality + Testing

**Priority: LOW | Effort: Medium | Impact: Maintenance and confidence**

| # | Task | Files | Est. |
|---|------|-------|------|
| 5.1 | Unify `_traverse_calls` / `_traverse_types` into generic BFS | `tools/navigation/hierarchy.py` | 30min |
| 5.2 | Move shared `_end_position_for_content` to `util/shared.py` | `tools/refactoring/helpers.py`, `backends/rope_backend.py`, `util/shared.py` | 20min |
| 5.3 | Share `_ensure_renameable` between refactoring and composite | `tools/refactoring/rename.py`, `tools/composite.py` | 20min |
| 5.4 | Add contract tests using in-memory transport | `tests/contract/` (new) | 2hr |

---

## Items Already Compliant

These best practices are already properly implemented:

| Best Practice | Implementation |
|--------------|----------------|
| Layered architecture (server → tools → backends) | `server.py` → `tools/` → `backends/` |
| Protocol-based decoupling | `_protocols.py` files in each tool package |
| Pydantic models for all inputs/outputs | `models.py` with Field validators |
| Tool annotations (readOnly, destructive) | `_READONLY`, `_DESTRUCTIVE` constants |
| Error hierarchy with proper chaining | `BackendError` → `PyrightError`/`JediError`/`RopeError` with `from exc` |
| Error boundary decorator | `_tool_error_boundary` catches all BackendError |
| Workspace path validation on all tools | `_tool_error_boundary` validates `_PATH_PARAMS` |
| Identifier validation on name params | `_tool_error_boundary` validates `_IDENTIFIER_PARAMS` |
| SignatureOperation.op enum validation | Pydantic `field_validator` in `models.py` |
| Lifespan management with cleanup | `app_lifespan` context manager |
| Atomic file writes | `write_atomic()` in `diff.py` |
| Safe defaults (apply=False) | All refactoring tools |
| Post-apply diagnostic validation | `attach_post_apply_diagnostics()` |
| Pyright request timeouts | Configurable via `PYRIGHT_REQUEST_TIMEOUT_SECONDS` |
| Pyright health check + auto-restart | `_ensure_healthy()` + `_restart()` |
| Rope operation timeouts | `asyncio.wait_for()` with `ROPE_OPERATION_TIMEOUT_SECONDS` |
| No stdout pollution | No `print()` calls anywhere |
| `ctx.debug` logging on all 45 tools | Consistent pattern |
| Sandboxed `eval()` in structural_search | AST pre-validation + restricted builtins |
| stdio transport with correct discipline | `mcp.run()` via FastMCP |
| Multi-backend fallback strategy | Pyright primary → Jedi fallback |
| Deduplication in results | `location_key()`, `diagnostic_key()` |
| Test infrastructure | 13 test files, unit + integration |
| MCP manifest for distribution | `manifest.json` |

---

## Items Not Applicable

| Best Practice | Reason |
|--------------|--------|
| OAuth / Authorization | stdio-only local server — no network transport |
| SSRF Prevention | No HTTP requests made by server |
| Session Management | stdio transport — no sessions |
| Resource subscriptions | No MCP resources exposed (tool-only server) |
| MCP Prompts | No MCP prompts exposed |
| Sampling | Not implemented (server doesn't request LLM completions) |
| Containerization | Local development tool, distributed as executable |
| Health check endpoints | stdio — no HTTP endpoints |

---

## Backlog Sync

Items in this plan that overlap with `ai_docs/backlog.md`:

| This Plan | Backlog Item | Status |
|-----------|-------------|--------|
| GAP-04 (Jedi timeouts) | P1: "Add timeouts to rope operations" (different backend but same pattern) | Rope done, Jedi still open |
| GAP-05 (Parallel scans) | P1: "Parallelize workspace-wide scans" | Open |
| GAP-07 (Silent errors) | P1: "Add logging to silent exception handlers" | Open |
| GAP-10 (semantic_tokens limit) | P1: "Add limit to get_semantic_tokens" | Open |
| GAP-12 (Code duplication) | P1: "Deduplicate BFS traversals" | Open |
| GAP-02 (Merge signature tools) | P1: "Merge get_signature_help + fallback" | Open |

New items from this analysis NOT in backlog:
- GAP-01: Workflow-oriented tool descriptions
- GAP-03: `idempotentHint` and `_ADDITIVE` annotations
- GAP-06: Structured logging with timing
- GAP-08: Concurrency semaphore for workspace scans
- GAP-09: Server description/instructions
- GAP-11: Contract tests
