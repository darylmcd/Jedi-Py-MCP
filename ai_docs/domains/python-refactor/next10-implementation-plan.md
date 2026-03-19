# Next-10 Implementation Plan

Purpose: formal plan for implementing the 10 new MCP tools and retrofitting existing 25 tools to match the MCP checklist.

## Part 1 — Existing Surface Audit (25 tools vs mcp-checklist.md)

### A. Server-Level Findings

| Checklist Item | Status | Notes |
|---|---|---|
| Capabilities explicitly declared | PASS | FastMCP auto-declares `tools` capability. |
| Tool names follow MCP naming (ASCII alnum + `_`) | PASS | All 25 tools use `snake_case`. |
| Every tool has `name`, `description`, `inputSchema` | PASS | Pydantic type hints + docstrings provide all three. |
| No-arg tools use strict empty schema | GAP | `get_workspace_diagnostics` only takes `ctx` — FastMCP handles this, but worth verifying in protocol output. |
| `isError: true` for domain/validation failures | GAP | `BackendError` subclasses propagate as unhandled exceptions. FastMCP wraps these as `isError: true` text content, but there is no explicit catch → structured error payload at the server layer. |
| Sensitive ops require explicit opt-in | PASS | All refactoring tools default `apply=False`. |
| Timeout/retry on backend APIs | GAP | No explicit timeout on Pyright LSP `request()` calls. A hung Pyright process blocks indefinitely. |
| Workspace path boundaries enforced | PASS | rope validates `relative_to(workspace_root)`. |
| Integration tests for success + failure | GAP | 11 integration tests cover only happy paths. No failure-path integration tests exist. |

### B. Per-Tool Common Gaps

| Checklist Item | Status | Action Needed |
|---|---|---|
| One-line purpose description | PASS | All tools have docstrings. |
| Input validation errors are specific | PARTIAL | Some tools (e.g., `call_hierarchy`) validate `direction`/`depth`; others silently accept bad input. |
| Output schema exists | PASS | FastMCP serializes Pydantic model schemas. |
| Non-destructive mode | PASS | All mutating tools have `apply=False`. |
| Description concrete enough for agent selection | PARTIAL | Terse descriptions like "Get type information" lack cues about when to pick this tool over alternatives. |
| At least two prompt examples | FAIL | Zero prompt examples exist for any tool. |
| Failure examples | FAIL | Zero failure/self-correction examples. |
| Results contain chaining context | PARTIAL | `RefactorResult.edits` chains to `diff_preview`; most analysis tools lack explicit "next step" context. |
| Unit tests: normal + invalid + fallback | PARTIAL | 56 unit tests cover normal and fallback paths. Invalid-input unit tests are sparse. |
| Integration tests: end-to-end | PARTIAL | 11 tests, success-only. |

### C. Prioritized Retrofit Items (Non-Blocking)

These can be done incrementally alongside the new-tool waves:

| ID | Retrofit Item | Priority | Effort |
|---|---|---|---|
| R1 | Add LSP request timeout (5 s default, configurable) to `PyrightLSPClient.request()`. | High | Small |
| R2 | Add explicit `BackendError → isError` handler in server tool wrappers via a shared decorator. | Medium | Small |
| R3 | Enrich tool docstrings with agent-facing selection cues (when to use/not use). | Medium | Small |
| R4 | Add prompt example bank in `mcp-checklist.md §E` for all 25 existing tools. | Low | Medium |
| R5 | Add 2–3 failure-path integration tests (bad file, bad line, bad rename). | Medium | Small |
| R6 | Add invalid-input unit tests for tools that lack them. | Low | Small |

## Part 2 — New Tool Implementation Plan (10 tools)

### New Models Required

| Model | Fields | Used By |
|---|---|---|
| `DocumentHighlight` | `range: Range`, `kind: str` (text/read/write) | `get_document_highlights` |
| `PrepareRenameResult` | `range: Range`, `placeholder: str` | `prepare_rename` |
| `InlayHint` | `position: Position`, `label: str`, `kind: str \| None`, `padding_left: bool`, `padding_right: bool` | `get_inlay_hints` |
| `SemanticToken` | `range: Range`, `token_type: str`, `modifiers: list[str]` | `get_semantic_tokens` |
| `FoldingRange` | `start_line: int`, `end_line: int`, `kind: str \| None` | `get_folding_ranges` |

Existing models reused: `Location`, `RefactorResult`, `SignatureInfo`.

### Wave E — Pyright Navigation (Simple LSP Delegates)

Three tools that follow the same pattern: call Pyright LSP → convert response → return model.

#### E1: `get_declaration`
- **Backend**: `PyrightLSPClient.get_declaration(file_path, line, char) → list[Location]`
- **LSP method**: `textDocument/declaration`
- **Tool layer**: `tools/navigation.py` — new `get_declaration()` function
- **Server**: register `get_declaration` tool; signature: `(file_path, line, character) → list[Location]`
- **Description**: "Navigate to the declaration site (stub/interface) for a symbol. Use when `goto_definition` returns an implementation but you need the interface or type stub."
- **Tests**: 1 unit (mock LSP response → Location list), 1 integration smoke

#### E2: `get_type_definition`
- **Backend**: `PyrightLSPClient.get_type_definition(file_path, line, char) → list[Location]`
- **LSP method**: `textDocument/typeDefinition`
- **Tool layer**: `tools/navigation.py` — new `get_type_definition()` function
- **Server**: register `get_type_definition` tool; signature: `(file_path, line, character) → list[Location]`
- **Description**: "Navigate to the type definition of a symbol. Returns the location where the type itself (class/protocol) is defined, not the variable assignment."
- **Tests**: 1 unit, 1 integration smoke

#### E3: `get_document_highlights`
- **Backend**: `PyrightLSPClient.get_document_highlights(file_path, line, char) → list[DocumentHighlight]`
- **LSP method**: `textDocument/documentHighlight`
- **Tool layer**: `tools/analysis.py` — new `get_document_highlights()` function
- **Server**: register `get_document_highlights` tool; signature: `(file_path, line, character) → list[DocumentHighlight]`
- **Description**: "Find all read/write usages of a symbol within a single file. Faster than `find_references` for local in-file usage clustering."
- **Tests**: 1 unit, 1 integration smoke

### Wave F — Pyright Pre-Flight + Enrichment

#### F1: `prepare_rename`
- **Backend**: `PyrightLSPClient.prepare_rename(file_path, line, char) → PrepareRenameResult | None`
- **LSP method**: `textDocument/prepareRename`
- **Tool layer**: `tools/refactoring.py` — new `prepare_rename()` function
- **Server**: register `prepare_rename` tool; signature: `(file_path, line, character) → PrepareRenameResult | None`
- **Description**: "Pre-flight check for rename validity. Returns the renameable range and placeholder text if the symbol can be renamed, or null if rename is not valid at this position. Use before calling `smart_rename` or `rename_symbol` to avoid failed refactors."
- **Tests**: 1 unit (valid symbol), 1 unit (non-renameable position → None), 1 integration smoke

#### F2: `get_inlay_hints`
- **Backend**: `PyrightLSPClient.get_inlay_hints(file_path, start_line, start_char, end_line, end_char) → list[InlayHint]`
- **LSP method**: `textDocument/inlayHint`
- **Tool layer**: `tools/analysis.py` — new `get_inlay_hints()` function
- **Server**: register `get_inlay_hints` tool; signature: `(file_path, start_line?, start_character?, end_line?, end_character?) → list[InlayHint]`
  - Defaults: full file range when start/end omitted.
- **Description**: "Get inlay hints (inferred types, parameter names) for a file range. Exposes Pyright's inferred type annotations and parameter name hints to improve code understanding without modifying source."
- **Tests**: 1 unit, 1 integration smoke

### Wave G — Pyright Structural

#### G1: `get_semantic_tokens`
- **Backend**: `PyrightLSPClient.get_semantic_tokens(file_path) → list[SemanticToken]`
- **LSP method**: `textDocument/semanticTokens/full`
- **Tool layer**: `tools/analysis.py` — new `get_semantic_tokens()` function
- **Server**: register `get_semantic_tokens` tool; signature: `(file_path) → list[SemanticToken]`
- **Description**: "Get full semantic token classification for a file. Returns token type (class, function, variable, parameter, etc.) and modifiers (definition, readonly, etc.) for symbol-kind-aware analysis."
- **Tests**: 1 unit (decode delta-encoded response), 1 integration smoke

#### G2: `get_folding_ranges`
- **Backend**: `PyrightLSPClient.get_folding_ranges(file_path) → list[FoldingRange]`
- **LSP method**: `textDocument/foldingRange`
- **Tool layer**: `tools/navigation.py` — new `get_folding_ranges()` function
- **Server**: register `get_folding_ranges` tool; signature: `(file_path) → list[FoldingRange]`
- **Description**: "Get folding ranges for a file. Returns logical code blocks (functions, classes, imports, comments) with line boundaries. Use to chunk large files into review/refactor windows for token-efficient planning."
- **Tests**: 1 unit, 1 integration smoke

### Wave H — Jedi Fallback + rope Refactoring

#### H1: `get_call_signatures_fallback`
- **Backend**: New `JediBackend.get_signatures(file_path, line, character) → SignatureInfo | None`
- **Jedi API**: `Script.get_signatures(line=line+1, column=character)`
- **Tool layer**: `tools/analysis.py` — new `get_call_signatures_fallback()` function
- **Server**: register `get_call_signatures_fallback` tool; signature: `(file_path, line, character) → SignatureInfo | None`
- **Description**: "Jedi-based signature help fallback. Use when `get_signature_help` (Pyright) returns null for dynamic or weakly-typed call sites."
- **Tests**: 1 unit (Jedi mock), 1 integration smoke

#### H2: `introduce_parameter`
- **Backend**: New `RopeBackend.introduce_parameter(file_path, line, character, parameter_name, default_value, apply) → RefactorResult`
- **rope API**: `rope.refactor.introduce_parameter.IntroduceParameter`
- **Tool layer**: `tools/refactoring.py` — new `introduce_parameter()` function
- **Server**: register `introduce_parameter` tool; signature: `(file_path, line, character, parameter_name, default_value, apply=False) → RefactorResult`
- **Description**: "Introduce a new parameter to a function, updating all call sites with the specified default value. Use for API evolution that must remain backward-compatible. Preview with `apply=False` first."
- **Tests**: 1 unit (rope mock), 1 unit (apply=True writes), 1 integration smoke

#### H3: `encapsulate_field`
- **Backend**: New `RopeBackend.encapsulate_field(file_path, line, character, apply) → RefactorResult`
- **rope API**: `rope.refactor.encapsulate_field.EncapsulateField`
- **Tool layer**: `tools/refactoring.py` — new `encapsulate_field()` function
- **Server**: register `encapsulate_field` tool; signature: `(file_path, line, character, apply=False) → RefactorResult`
- **Description**: "Convert direct attribute access into managed property access (getter/setter). Use for staged encapsulation refactors. Preview with `apply=False` first."
- **Tests**: 1 unit (rope mock), 1 unit (apply=True writes), 1 integration smoke

## Part 3 — Execution Plan

### Implementation Order

| Phase | Work Items | Changes |
|---|---|---|
| **Phase 0: Retrofit foundations** | R1 (LSP timeout), R2 (error decorator) | `pyright_lsp.py`, `server.py` |
| **Phase 1: Wave E** | E1–E3 + models | `models.py`, `pyright_lsp.py`, `navigation.py`, `analysis.py`, `server.py`, unit + integration tests |
| **Phase 2: Wave F** | F1–F2 + models | `models.py`, `pyright_lsp.py`, `refactoring.py`, `analysis.py`, `server.py`, unit + integration tests |
| **Phase 3: Wave G** | G1–G2 + models | `models.py`, `pyright_lsp.py`, `analysis.py`, `navigation.py`, `server.py`, unit + integration tests |
| **Phase 4: Wave H** | H1–H3 | `models.py`, `jedi_backend.py`, `rope_backend.py`, `analysis.py`, `refactoring.py`, `server.py`, unit + integration tests |
| **Phase 5: Retrofit polish** | R3 (docstrings), R5 (failure integration tests), R6 (invalid-input unit tests) | `server.py`, tests |
| **Phase 6: Docs + checklist** | Update reference.md tool table, README tool table, mcp-checklist.md §E prompt bank, backlog.md | docs only |

### Per-Phase Validation Gate

Every phase must pass before moving to the next:
```
python -m ruff check .
python -m pyright .
python -m mypy .
python -m pytest tests/unit/ -v
./scripts/test-integration.ps1
```

### Estimated Deliverables Summary

| Metric | Current | After All Phases |
|---|---|---|
| MCP tools | 25 | 35 |
| Pydantic models | 18 | 23 |
| Pyright backend methods | 16 | 23 |
| Jedi backend methods | 5 | 6 |
| rope backend methods | 5 | 7 |
| Unit tests | 56 | ~78 |
| Integration tests | 11 | ~22 |

### Prioritization Rubric Scores (from mcp-checklist §F)

| Tool | Agent Utility | Safety | Complexity | Testability | Chainability | Total |
|---|---|---|---|---|---|---|
| `prepare_rename` | 5 | 5 | 4 | 5 | 5 | 24 |
| `get_type_definition` | 5 | 5 | 5 | 4 | 5 | 24 |
| `get_declaration` | 4 | 5 | 5 | 4 | 5 | 23 |
| `get_document_highlights` | 4 | 5 | 5 | 4 | 4 | 22 |
| `get_folding_ranges` | 4 | 5 | 5 | 4 | 4 | 22 |
| `introduce_parameter` | 5 | 3 | 3 | 4 | 4 | 19 |
| `get_inlay_hints` | 4 | 5 | 4 | 3 | 3 | 19 |
| `encapsulate_field` | 4 | 3 | 3 | 4 | 4 | 18 |
| `get_call_signatures_fallback` | 3 | 5 | 4 | 3 | 3 | 18 |
| `get_semantic_tokens` | 3 | 5 | 3 | 3 | 3 | 17 |

### New Agent Workflow Patterns

#### Pre-flight rename
1. `prepare_rename(file, line, char)` — confirm rename is valid + get placeholder.
2. `find_references(file, line, char)` — assess blast radius.
3. `smart_rename(file, line, char, new_name, apply=False)` → `diff_preview(edits)`.

#### Navigate from variable to type
1. `get_type_info(file, line, char)` — get type string.
2. `get_type_definition(file, line, char)` — jump to where the type is defined.
3. `get_symbol_outline(file_path=<type_file>)` — explore the type's structure.

#### Chunk a large file for review
1. `get_folding_ranges(file)` — get logical blocks.
2. `get_symbol_outline(file)` — overlay with symbol tree.
3. Process chunks sequentially for token-efficient analysis.

#### In-file usage analysis
1. `get_document_highlights(file, line, char)` — fast local read/write map.
2. `find_references(file, line, char)` — if cross-file scope is needed.

### Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Pyright may not support `textDocument/declaration` (often returns same as definition) | Graceful fallback: return definition results when declaration returns null/empty. |
| `semanticTokens/full` response is delta-encoded and complex | Implement careful decode with comprehensive unit test coverage. |
| `rope.refactor.introduce_parameter` may have edge cases with decorators/defaults | Test against multiple function signatures; wrap with clear error messages. |
| `rope.refactor.encapsulate_field` may not work with all attribute patterns | Restrict to simple instance attributes initially; document limitations. |
| LSP timeout addition may break existing tests that mock without timeouts | Add timeout as keyword arg with generous default; mock tests unaffected. |

## Approval Requested

Approve this plan to proceed with implementation starting from Phase 0.
