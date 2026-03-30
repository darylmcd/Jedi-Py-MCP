# MCP Tooling Checklist (Current + New)

Purpose: a practical checklist for validating current MCP tools and any new tool/prompt additions against MCP best practices.

## Source References

- Tools spec (latest): https://modelcontextprotocol.io/specification/latest/server/tools
- Prompts spec (latest): https://modelcontextprotocol.io/specification/latest/server/prompts
- Server concepts: https://modelcontextprotocol.io/docs/learn/server-concepts

Key principles pulled from MCP docs:
- Tools are model-controlled, prompts are user-controlled.
- Input schema is required and should be strict for predictable behavior.
- Output schema is strongly recommended for structured results.
- Use tool execution errors (`isError: true`) for actionable, recoverable failures.
- Keep humans in the loop for sensitive or destructive operations.

## A. Server-Level Checklist

- [ ] Capabilities are explicitly declared and accurate (`tools`, `prompts` when implemented).
- [ ] Tool names follow MCP naming guidance (ASCII alnum + `_` `-` `.`; unique).
- [ ] Every tool has clear `name`, `description`, and strongly typed `inputSchema`.
- [ ] Tools with no args use `{"type":"object","additionalProperties":false}`.
- [ ] Structured responses use `structuredContent` and optionally mirrored text for compatibility.
- [ ] Error strategy is consistent:
  - [ ] Protocol errors for malformed requests.
  - [ ] `isError: true` for domain/validation/runtime failures that an LLM can self-correct.
- [ ] Sensitive operations require explicit user intent and support preview/dry-run.
- [ ] Tool calls include timeout/retry boundaries where backend APIs may block.
- [ ] Path and workspace boundaries are enforced for file-modifying operations.
- [ ] Integration tests verify both success and expected failure behavior.

## B. Tool-By-Tool Checklist Template

Use this for each existing or proposed tool.

### 1) Contract
- [ ] Tool has a one-line purpose statement.
- [ ] Input fields are minimal and unambiguous.
- [ ] Input validation errors are specific and actionable.
- [ ] Output includes stable fields; order and sorting are deterministic where relevant.
- [ ] Output schema exists (recommended for all structured outputs).

### 2) Safety
- [ ] Non-destructive mode exists where applicable (`apply=False` or equivalent).
- [ ] Destructive mode requires explicit opt-in.
- [ ] Writes are atomic and bounded to workspace root.
- [ ] Diagnostics/verification after mutation is provided where practical.

### 3) Agent UX
- [ ] Description is concrete enough for autonomous selection.
- [ ] At least two prompt examples exist (happy path + edge case).
- [ ] Failure examples exist and show self-correctable next step.
- [ ] Results contain enough context for chaining to the next tool.

### 4) Quality Gates
- [ ] Unit tests cover normal path, invalid input, and fallback behavior.
- [ ] Integration tests cover end-to-end invocation through MCP transport.
- [ ] Lint/type/test matrix passes on target runtime.

## C. Current Surface Coverage (Snapshot)

Current server exposes 75 tools across analysis/navigation/refactoring/search/metrics/composite. Coverage should be reviewed against sections A and B whenever tools are added or modified.

Minimum per-release checks for current tools:
- [ ] Tool table in `README.md` matches actual server registration.
- [ ] Domain reference in `ai_docs/domains/python-refactor/reference.md` is current.
- [ ] Integration lane (`./scripts/test-integration.ps1`) remains green.
- [ ] CI workflow includes lint, type checks, unit tests, integration tests.

## D. New Tool Intake Checklist (for Next 10 picks)

For each candidate from the roadmap:
- [ ] Confirm backend API exists and is stable (Pyright/Jedi/rope).
- [ ] Define MCP request args and response model first.
- [ ] Add server registration and domain docs in same change.
- [ ] Add unit tests for conversion/mapping and error handling.
- [ ] Add at least one integration smoke test.
- [ ] Add prompt examples to this checklist section (see template below).

## E. Prompt Example Template (Per Tool)

Add a short prompt bank for every tool you expose.

### Template
- Goal prompt:
  - "Use `<tool_name>` to <goal> for `<file_or_symbol>`. Return only key fields: <fields>."
- Validation prompt:
  - "Run `<tool_name>` with intentionally invalid `<arg>` and show expected error handling."
- Chaining prompt:
  - "Use output of `<tool_name_a>` as input to `<tool_name_b>` and summarize the final actionable step."

### Example (existing tool: `organize_imports`)
- Goal:
  - "Run `organize_imports` on `src/python_refactor_mcp/server.py` with `apply=false`, then summarize proposed edits count."
- Validation:
  - "Run `organize_imports` on a non-existent file and show the exact error returned."
- Chaining:
  - "Preview `organize_imports`, then feed edits to `diff_preview` and summarize top 3 hunks."

### Example (candidate tool: `prepare_rename`)
- Goal:
  - "Run `prepare_rename` on symbol under cursor and return whether rename is valid plus editable range."
- Validation:
  - "Attempt `prepare_rename` on a string literal and explain why rename is invalid."
- Chaining:
  - "Use `prepare_rename` first; only if valid, call `smart_rename` with `apply=false` and summarize impact."

### New Tool Prompt Bank (Implemented)

- `get_declaration`:
  - Goal: "Run `get_declaration` for symbol at cursor and return only file path and start line."
  - Validation: "Run `get_declaration` on whitespace and show empty-result handling."
  - Chaining: "Use `get_declaration` output to call `get_symbol_outline` on the declaration file."
- `get_type_definition`:
  - Goal: "Run `get_type_definition` and return the target type file and symbol range."
  - Validation: "Run `get_type_definition` on a literal and report fallback/empty behavior."
  - Chaining: "Resolve a variable with `get_type_info`, then call `get_type_definition` and summarize concrete type origin."
- `get_document_highlights`:
  - Goal: "Run `get_document_highlights` and group counts by highlight kind (read/write/text)."
  - Validation: "Run `get_document_highlights` at an invalid position and show the returned tool error."
  - Chaining: "Use `get_document_highlights` first; if broad scope is needed, escalate to `find_references`."
- `get_inlay_hints`:
  - Goal: "Run `get_inlay_hints` for the full file and return top 10 hints by position."
  - Validation: "Run `get_inlay_hints` on a missing file and show exact error behavior."
  - Chaining: "Use `get_inlay_hints`, then call `get_semantic_tokens` and compare inferred types with token classes."
- `get_semantic_tokens`:
  - Goal: "Run `get_semantic_tokens` and summarize token counts by token_type."
  - Validation: "Run `get_semantic_tokens` for a file unsupported by backend and explain empty-result handling."
  - Chaining: "Use `get_semantic_tokens` to identify high-density regions, then call `get_folding_ranges` to chunk review windows."
- `get_folding_ranges`:
  - Goal: "Run `get_folding_ranges` and return only start_line/end_line/kind."
  - Validation: "Run `get_folding_ranges` on an invalid path and report the tool error."
  - Chaining: "Use `get_folding_ranges` to split file sections, then call `get_symbol_outline` per section target."
- `get_call_signatures_fallback`:
  - Goal: "Run `get_call_signatures_fallback` at callsite and return signature label + active parameter."
  - Validation: "Run `get_call_signatures_fallback` outside a call expression and show null response handling."
  - Chaining: "Call `get_signature_help`; if null, call `get_call_signatures_fallback` and continue with returned signature context."
- `introduce_parameter`:
  - Goal: "Run `introduce_parameter` with `apply=false` and summarize files_affected and edits count."
  - Validation: "Run `introduce_parameter` on non-callable symbol and show corrective error guidance."
  - Chaining: "Preview `introduce_parameter`, pass edits to `diff_preview`, then re-run with `apply=true` if accepted."
- `encapsulate_field`:
  - Goal: "Run `encapsulate_field` with `apply=false` and summarize generated accessor-related edits."
  - Validation: "Run `encapsulate_field` on unsupported target and show explicit failure message."
  - Chaining: "Preview `encapsulate_field`, then call `get_diagnostics` on affected files before applying."

## F. Prioritization Rubric

Score each new tool from 1-5 in each category:
- Agent utility (frequency + impact)
- Safety risk (lower risk = higher score)
- Implementation complexity (lower complexity = higher score)
- Testability and determinism
- Chainability with existing tools

Implement highest total first; defer low-testability/high-risk tools.
