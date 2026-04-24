# MCP Tooling Checklist (Current + New)
<!-- purpose: Checklist for validating MCP tools against best practices; includes prompt example bank. -->

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

Current server exposes 87 tools across analysis/navigation/refactoring/search/metrics/composite. Coverage should be reviewed against sections A and B whenever tools are added or modified.

Minimum per-release checks for current tools:
- [ ] Tool table in `README.md` matches actual server registration.
- [ ] Domain reference in `ai_docs/domains/python-refactor/reference.md` is current.
- [ ] Integration lane (`./scripts/test-integration.ps1`) remains green.
- [ ] CI workflow includes lint, type checks, unit tests, integration tests.

## D. New Tool Intake Checklist (for Next 10 picks)

For each candidate from the roadmap:
- [ ] Confirm backend API exists and is stable (Pyright/Jedi/rope) — record the verification in the backlog row's `blocker` column (`none`, `custom-cst`, `rope-api-absent`, `redundant-with-X`, etc.).
- [ ] Define MCP request args and response model first.
- [ ] Add server registration and domain docs in same change.
- [ ] Add unit tests for conversion/mapping and error handling.
- [ ] Add at least one integration smoke test.
- [ ] Add prompt examples to this checklist section (see template below).

**Candidate storage:** roadmap candidates live in [`ai_docs/backlog.md`](../../backlog.md) as rows prefixed `cand-*`, governed by that file's Agent contract (stable ids, pruned on ship). This file stays focused on the intake *process* and on coverage documentation for *shipped* tools.

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
  - "Use `prepare_rename` first; only if valid, call `rename_symbol` with `apply=false` and summarize impact."

### Tool Prompt Bank

Every tool on the current server has a Goal / Validation / Chaining prompt triple. Organized by category to match the server registration; see `ai_docs/domains/python-refactor/reference.md` for full contract details.

#### Navigation & lookups

- `goto_definition`:
  - Goal: "Run `goto_definition` at the cursor and return only the target file path and start line."
  - Validation: "Run `goto_definition` on a whitespace position and show the empty-result response."
  - Chaining: "Use `goto_definition`, then call `get_symbol_outline` on the target file to locate sibling members."
- `get_declaration`:
  - Goal: "Run `get_declaration` for symbol at cursor and return only file path and start line."
  - Validation: "Run `get_declaration` on whitespace and show empty-result handling."
  - Chaining: "Use `get_declaration` output to call `get_symbol_outline` on the declaration file."
- `get_type_definition`:
  - Goal: "Run `get_type_definition` and return the target type file and symbol range."
  - Validation: "Run `get_type_definition` on a literal and report fallback/empty behavior."
  - Chaining: "Resolve a variable with `get_type_info`, then call `get_type_definition` and summarize concrete type origin."
- `call_hierarchy`:
  - Goal: "Run `call_hierarchy` on a function and return direct callers grouped by module."
  - Validation: "Run `call_hierarchy` on a private helper with zero callers and confirm the empty-caller envelope."
  - Chaining: "Call `call_hierarchy`, pick the highest-fanout caller, then run `find_references` on it."
- `find_references`:
  - Goal: "Run `find_references` for a public API and return only file + line, deduped by file."
  - Validation: "Run `find_references` on an identifier inside a string literal and show the non-symbol response."
  - Chaining: "Before `rename_symbol`, run `find_references` to size impact; bail if >200 sites."
- `find_implementations`:
  - Goal: "Run `find_implementations` on a protocol method and list each concrete class."
  - Validation: "Run `find_implementations` on a non-abstract function and show the empty/invalid-target response."
  - Chaining: "Call `find_implementations`, then `goto_definition` on each to confirm source ownership."
- `prepare_rename`:
  - Goal: "Run `prepare_rename` at cursor and return whether rename is valid plus editable range."
  - Validation: "Attempt `prepare_rename` on a keyword and explain why rename is invalid."
  - Chaining: "Use `prepare_rename` first; only if valid, call `rename_symbol` with `apply=false`."
- `selection_range`:
  - Goal: "Run `selection_range` at cursor and return the outermost enclosing range only."
  - Validation: "Run `selection_range` on an out-of-bounds position and show the validation error."
  - Chaining: "Use `selection_range` to find a containing block, then pass that range to `extract_method`."
- `get_context`:
  - Goal: "Run `get_context` at cursor and summarize enclosing class/function names."
  - Validation: "Run `get_context` at column 0 of an empty line and show the minimal-context response."
  - Chaining: "Call `get_context`, then `get_symbol_outline` of the enclosing container for peer members."
- `get_symbol_outline`:
  - Goal: "Run `get_symbol_outline` on a file and return only top-level class/function names."
  - Validation: "Run `get_symbol_outline` on a non-Python file and show the empty/invalid response."
  - Chaining: "Use `get_symbol_outline` to discover a target symbol, then `goto_definition` on it."
- `get_sub_definitions`:
  - Goal: "Run `get_sub_definitions` on a class and return its methods + nested classes."
  - Validation: "Run `get_sub_definitions` on a module-level constant and show the leaf-node response."
  - Chaining: "Use `get_sub_definitions` for scope discovery, then feed each child to `get_documentation`."
- `type_hierarchy`:
  - Goal: "Run `type_hierarchy` on a class and return both supertypes and subtypes, grouped."
  - Validation: "Run `type_hierarchy` on a non-class symbol and show the invalid-target envelope."
  - Chaining: "Call `type_hierarchy`, then `find_implementations` on the root for a full inheritance graph."
- `get_all_names`:
  - Goal: "Run `get_all_names` on a module and return the exported public-name list only."
  - Validation: "Run `get_all_names` on a file with no `__all__` and confirm fallback enumeration behavior."
  - Chaining: "Use `get_all_names` to bound a rename scope, then `find_references` on each exported name."
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
- `get_signature_help`:
  - Goal: "Run `get_signature_help` at callsite and return signature label + active parameter."
  - Validation: "Run `get_signature_help` outside a call expression and show null response handling."
  - Chaining: "Call `get_signature_help`; if null, call `get_documentation` for fallback context."
- `get_completions`:
  - Goal: "Run `get_completions` at cursor and return the first 10 entries with kind + label."
  - Validation: "Run `get_completions` inside a string literal and confirm the empty-completion response."
  - Chaining: "Use `get_completions` to discover an attribute name, then `goto_definition` on the chosen entry."

#### Analysis

- `get_diagnostics`:
  - Goal: "Run `get_diagnostics` on a file and return only errors (severity=error)."
  - Validation: "Run `get_diagnostics` on a non-existent path and show the exact validation error."
  - Chaining: "After any refactor apply, call `get_diagnostics` on affected files to gate acceptance."
- `get_workspace_diagnostics`:
  - Goal: "Run `get_workspace_diagnostics` and summarize the top 5 files by error count."
  - Validation: "Run `get_workspace_diagnostics` on a workspace with no Python files and confirm empty result."
  - Chaining: "Use `get_workspace_diagnostics` to pick a hot file, then `get_diagnostics` for detail."
- `get_syntax_errors`:
  - Goal: "Run `get_syntax_errors` on a file and return line/col of each parse failure."
  - Validation: "Run `get_syntax_errors` on well-formed code and confirm the empty-array response."
  - Chaining: "Call `get_syntax_errors` first; only if clean, proceed to type-level tools like `get_type_info`."
- `get_type_info`:
  - Goal: "Run `get_type_info` at cursor and return declared type + inferred type."
  - Validation: "Run `get_type_info` in a comment and show the no-symbol response."
  - Chaining: "Use `get_type_info`, then `get_type_definition` to jump to the concrete type."
- `get_type_hint_string`:
  - Goal: "Run `get_type_hint_string` at cursor and return a single insert-ready annotation."
  - Validation: "Run `get_type_hint_string` on an unanalyzable expression and show the fallback."
  - Chaining: "Call `get_type_hint_string`, then `apply_code_action` for 'add type annotation'."
- `get_type_coverage`:
  - Goal: "Run `get_type_coverage` on a module and return the annotated / total ratio."
  - Validation: "Run `get_type_coverage` on an empty file and confirm the zero-over-zero envelope."
  - Chaining: "Rank modules by `get_type_coverage`, then run `create_type_stubs` on the worst."
- `get_test_coverage_map`:
  - Goal: "Run `get_test_coverage_map` for a source file and return uncovered line ranges."
  - Validation: "Run `get_test_coverage_map` without prior coverage data and show the missing-data message."
  - Chaining: "Use `get_test_coverage_map` to target untested code, then `get_symbol_outline` to draft tests."
- `find_errors_static`:
  - Goal: "Run `find_errors_static` on a file and summarize the top 5 error categories."
  - Validation: "Run `find_errors_static` on a clean module and confirm zero findings."
  - Chaining: "Use `find_errors_static` to locate an issue, then `apply_code_action` to suggest a fix."
- `find_constructors`:
  - Goal: "Run `find_constructors` for a class and return each `__init__` / factory signature."
  - Validation: "Run `find_constructors` on a dataclass-only class and show synthetic-ctor handling."
  - Chaining: "Use `find_constructors` output as input to `change_signature` to update call sites."
- `deep_type_inference`:
  - Goal: "Run `deep_type_inference` on an expression and return the narrowed type chain."
  - Validation: "Run `deep_type_inference` on `Any` and confirm the inference-limit envelope."
  - Chaining: "Call `deep_type_inference`; if specific enough, pass to `get_type_hint_string` for insertion."
- `check_layer_violations`:
  - Goal: "Run `check_layer_violations` and return only cross-layer imports with source + target modules."
  - Validation: "Run `check_layer_violations` with no layering config and show the missing-config response."
  - Chaining: "Use `check_layer_violations`, then `move_module` to relocate offending modules into the correct layer."
- `interface_conformance`:
  - Goal: "Run `interface_conformance` for a class against a Protocol and list missing members."
  - Validation: "Run `interface_conformance` against a non-Protocol target and show the type-mismatch error."
  - Chaining: "Use `interface_conformance` gaps as input to `extract_protocol` or member-add code actions."
- `security_scan`:
  - Goal: "Run `security_scan` on the workspace and return only High/Critical findings."
  - Validation: "Run `security_scan` on an empty workspace and confirm no-findings envelope."
  - Chaining: "Call `security_scan`, then `get_diagnostics` on each flagged file for inline context."
- `simulate_execution`:
  - Goal: "Run `simulate_execution` on a function and return the predicted return-type + side-effect list."
  - Validation: "Run `simulate_execution` on code raising at import time and show the trapped-error envelope."
  - Chaining: "Use `simulate_execution` pre-refactor, re-run post-apply, and diff predicted effects."
- `get_documentation`:
  - Goal: "Run `get_documentation` at cursor and return docstring first paragraph only."
  - Validation: "Run `get_documentation` on an undocumented builtin and confirm empty-doc handling."
  - Chaining: "Call `get_documentation`; if empty, call `get_type_info` for at-least-signature context."
- `get_keyword_help`:
  - Goal: "Run `get_keyword_help` for `match` and return a one-line summary."
  - Validation: "Run `get_keyword_help` on a non-keyword identifier and show the validation error."
  - Chaining: "Use `get_keyword_help` to confirm language semantics before suggesting a `restructure`."

#### Search

- `search_symbols`:
  - Goal: "Run `search_symbols` for `load_*` and return top 10 matches with kind + path."
  - Validation: "Run `search_symbols` with empty query and confirm the guard-clause rejection."
  - Chaining: "Use `search_symbols` to locate a candidate, then `goto_definition` to confirm identity."
- `project_search`:
  - Goal: "Run `project_search` for a literal string and return paths + line counts."
  - Validation: "Run `project_search` with a regex of unbalanced parens and show the regex-error envelope."
  - Chaining: "Use `project_search` to find a text occurrence, then `find_references` to widen into symbol scope."
- `structural_search`:
  - Goal: "Run `structural_search` for `except Exception: pass` and return each match location."
  - Validation: "Run `structural_search` with a malformed pattern and show the parse-error response."
  - Chaining: "Use `structural_search` matches as candidates for `apply_code_action` or `restructure`."
- `dead_code_detection`:
  - Goal: "Run `dead_code_detection` and return only unreferenced public functions."
  - Validation: "Run `dead_code_detection` on a package where every symbol is exported and confirm zero findings."
  - Chaining: "Feed `dead_code_detection` results into `find_references` to confirm zero sites before deleting."
- `find_duplicated_code`:
  - Goal: "Run `find_duplicated_code` and return the top 3 clones by size."
  - Validation: "Run `find_duplicated_code` on a single-file project and confirm empty result."
  - Chaining: "Use `find_duplicated_code` hot spots as input to `extract_method` or `use_function`."
- `suggest_imports`:
  - Goal: "Run `suggest_imports` for an unresolved name and return ranked import candidates."
  - Validation: "Run `suggest_imports` on an already-imported name and confirm no-op response."
  - Chaining: "Use top-ranked `suggest_imports` result, then `organize_imports` to normalize placement."
- `find_unused_imports`:
  - Goal: "Run `find_unused_imports` on a file and return a per-line removal list."
  - Validation: "Run `find_unused_imports` on a file with only used imports and confirm empty output."
  - Chaining: "Use `find_unused_imports`, then `organize_imports` with `apply=true` to clean + sort in one pass."
- `autoimport_search`:
  - Goal: "Run `autoimport_search` for `Path` and return exact module:name candidates."
  - Validation: "Run `autoimport_search` on an empty query and show the input-validation error."
  - Chaining: "Pair `autoimport_search` with `suggest_imports` when multiple tool hits disagree."

#### Refactoring (apply-gated)

- `rename_symbol`:
  - Goal: "Run `rename_symbol` with `apply=false` and summarize files_affected + edits count."
  - Validation: "Run `rename_symbol` to a syntactically invalid name and show the validation error."
  - Chaining: "Run `prepare_rename`, then `find_references`, then `rename_symbol` with `apply=true`."
- `multi_project_rename`:
  - Goal: "Run `multi_project_rename` across two workspaces with `apply=false` and list touched repos."
  - Validation: "Run `multi_project_rename` with a missing workspace root and show the resolution error."
  - Chaining: "Run `multi_project_rename` preview, then `get_diagnostics` per workspace before apply."
- `extract_method`:
  - Goal: "Run `extract_method` on a selection with `apply=false` and return the new method signature."
  - Validation: "Run `extract_method` on a range spanning two functions and show the scope-violation error."
  - Chaining: "Call `selection_range`, then `extract_method` on the outermost expression range."
- `extract_variable`:
  - Goal: "Run `extract_variable` on an expression with `apply=false` and return proposed local name."
  - Validation: "Run `extract_variable` on an assignment LHS and show the invalid-target error."
  - Chaining: "Use `extract_variable`, then `rename_symbol` to finalize the local's name."
- `extract_protocol`:
  - Goal: "Run `extract_protocol` from a class with `apply=false` and return the proposed Protocol body."
  - Validation: "Run `extract_protocol` on a class with no public methods and show the empty-protocol response."
  - Chaining: "Run `extract_protocol`, then `interface_conformance` on the origin class to confirm match."
- `inline_method`:
  - Goal: "Run `inline_method` on a one-call-site helper with `apply=false` and show the substituted body."
  - Validation: "Run `inline_method` on a recursive method and show the unsafe-inline error."
  - Chaining: "Call `find_references` first; only inline if callers == 1, then `inline_method` apply."
- `inline_variable`:
  - Goal: "Run `inline_variable` on a single-use local with `apply=false` and return the rewritten expression."
  - Validation: "Run `inline_variable` on a variable mutated after assignment and show the unsafe error."
  - Chaining: "Use `get_document_highlights` to confirm single-read before `inline_variable` apply."
- `inline_parameter`:
  - Goal: "Run `inline_parameter` with `apply=false` and return affected call-site count."
  - Validation: "Run `inline_parameter` on a parameter with non-literal arguments and show the unsafe-inline error."
  - Chaining: "Run `find_references` on the function, then `inline_parameter` only if all call-sites are constant."
- `introduce_parameter`:
  - Goal: "Run `introduce_parameter` with `apply=false` and summarize files_affected and edits count."
  - Validation: "Run `introduce_parameter` on non-callable symbol and show corrective error guidance."
  - Chaining: "Preview `introduce_parameter`, pass edits to `diff_preview`, then re-run with `apply=true` if accepted."
- `introduce_factory`:
  - Goal: "Run `introduce_factory` on a class with `apply=false` and return the proposed factory signature."
  - Validation: "Run `introduce_factory` on a class without `__init__` and show the missing-ctor error."
  - Chaining: "Use `introduce_factory` preview, then `find_constructors` to confirm call-site routing."
- `move_symbol`:
  - Goal: "Run `move_symbol` with `apply=false` and return import-rewrite count at each call site."
  - Validation: "Run `move_symbol` with source == destination path and show the no-op rejection."
  - Chaining: "Preview `move_symbol`, then `organize_imports` on the destination to normalize order."
- `move_method`:
  - Goal: "Run `move_method` to another class with `apply=false` and return self/static conversion summary."
  - Validation: "Run `move_method` to a destination lacking required attributes and show the host-mismatch error."
  - Chaining: "Call `move_method`, then `get_diagnostics` on both classes before apply."
- `move_module`:
  - Goal: "Run `move_module` with `apply=false` and return rewritten-import count."
  - Validation: "Run `move_module` into itself and show the cycle-prevention error."
  - Chaining: "Preview `move_module`, then `check_layer_violations` on the new location."
- `module_to_package`:
  - Goal: "Run `module_to_package` with `apply=false` and return the new `__init__.py` shape."
  - Validation: "Run `module_to_package` on an already-package directory and show the no-op response."
  - Chaining: "Use `module_to_package` apply, then `organize_imports` across downstream modules."
- `encapsulate_field`:
  - Goal: "Run `encapsulate_field` with `apply=false` and summarize generated accessor-related edits."
  - Validation: "Run `encapsulate_field` on unsupported target and show explicit failure message."
  - Chaining: "Preview `encapsulate_field`, then call `get_diagnostics` on affected files before applying."
- `local_to_field`:
  - Goal: "Run `local_to_field` on a method local with `apply=false` and return the proposed self-attribute name."
  - Validation: "Run `local_to_field` outside a method and show the scope-error envelope."
  - Chaining: "Run `local_to_field` preview, then `encapsulate_field` to add accessors if needed."
- `method_object`:
  - Goal: "Run `method_object` on a long method with `apply=false` and return the proposed class name + members."
  - Validation: "Run `method_object` on a one-line method and show the triviality-reject envelope."
  - Chaining: "Preview `method_object`, then `get_symbol_outline` on the new class to confirm shape."
- `change_signature`:
  - Goal: "Run `change_signature` to add a parameter with `apply=false` and list affected call-sites."
  - Validation: "Run `change_signature` with duplicate parameter names and show the validation error."
  - Chaining: "Call `find_references`, then `change_signature`; confirm all sites with `get_diagnostics` post-apply."
- `argument_default_inliner`:
  - Goal: "Run `argument_default_inliner` on a function and list call sites that still pass the default."
  - Validation: "Run `argument_default_inliner` on a function without defaults and show the no-target response."
  - Chaining: "Use inliner preview, then `change_signature` to drop the parameter once all sites are stripped."
- `argument_normalizer`:
  - Goal: "Run `argument_normalizer` with `apply=false` and return positional→keyword conversion count."
  - Note: Known upstream issue — rope's normalizer strips Python 3 type annotations (see `known-rope-annotations` in backlog)."
  - Validation: "Run `argument_normalizer` on a callsite with `*args` and show the limitation response."
  - Chaining: "Run `argument_normalizer` preview, diff with `diff_preview`, then verify annotations survived before apply."
- `restructure`:
  - Goal: "Run `restructure` with a pattern→replacement pair and `apply=false`, then list match sites."
  - Validation: "Run `restructure` with a pattern that fails to parse and show the parse error."
  - Chaining: "Use `structural_search` to preview matches, then `restructure` to apply the edit."
- `use_function`:
  - Goal: "Run `use_function` to replace an inlined expression with a helper call, `apply=false`, list sites."
  - Validation: "Run `use_function` on a helper with incompatible arity and show the mismatch error."
  - Chaining: "Pair with `find_duplicated_code`: pick a duplicate block, then `use_function` to dedupe."
- `generate_code`:
  - Goal: "Run `generate_code` to emit a dataclass stub and return the new file path."
  - Validation: "Run `generate_code` with an unknown template id and show the invalid-template error."
  - Chaining: "Use `generate_code`, then `get_diagnostics` on the emitted file to verify it's clean."
- `expand_star_imports`:
  - Goal: "Run `expand_star_imports` on a module with `apply=false` and return explicit-name list."
  - Validation: "Run `expand_star_imports` on a file with no star imports and confirm no-op response."
  - Chaining: "Run `expand_star_imports`, then `find_unused_imports` to trim what actually isn't used."
- `froms_to_imports`:
  - Goal: "Run `froms_to_imports` on a module with `apply=false` and return conversion count."
  - Validation: "Run `froms_to_imports` on a module without `from` imports and confirm no-op."
  - Chaining: "Use `froms_to_imports`, then `organize_imports` to sort the rewritten block."
- `relatives_to_absolutes`:
  - Goal: "Run `relatives_to_absolutes` on a package with `apply=false` and return rewritten-import count."
  - Validation: "Run `relatives_to_absolutes` on a top-level module and confirm no-relative no-op."
  - Chaining: "Apply `relatives_to_absolutes`, then `check_layer_violations` to verify module ownership."
- `fix_module_names`:
  - Goal: "Run `fix_module_names` with `apply=false` and return the rename plan per file."
  - Validation: "Run `fix_module_names` on a package with already-PEP8 names and confirm no-op."
  - Chaining: "Preview `fix_module_names`, then `move_module` if physical relocation is needed."
- `handle_long_imports`:
  - Goal: "Run `handle_long_imports` with `apply=false` and return lines exceeding the configured limit."
  - Validation: "Run `handle_long_imports` with line-limit=0 and show the invalid-config error."
  - Chaining: "Run `handle_long_imports`, then `organize_imports` to finalize grouping."
- `organize_imports`:
  - Goal: "Run `organize_imports` on `src/python_refactor_mcp/server.py` with `apply=false`, then summarize proposed edits count."
  - Validation: "Run `organize_imports` on a non-existent file and show the exact error returned."
  - Chaining: "Preview `organize_imports`, then feed edits to `diff_preview` and summarize top 3 hunks."
- `apply_code_action`:
  - Goal: "Run `apply_code_action` for a quick-fix at a diagnostic and return the resulting text edits."
  - Validation: "Run `apply_code_action` with an unknown action id and show the not-found error."
  - Chaining: "Call `get_diagnostics`, pick an action from its `relatedActions`, then `apply_code_action`."

#### Metrics

- `code_metrics`:
  - Goal: "Run `code_metrics` on a file and return cyclomatic complexity per function, sorted desc."
  - Validation: "Run `code_metrics` on an empty file and confirm the zero-metrics envelope."
  - Chaining: "Rank hot spots with `code_metrics`, then `extract_method` on the top complexity offender."
- `get_coupling_metrics`:
  - Goal: "Run `get_coupling_metrics` on a package and return afferent/efferent counts per module."
  - Validation: "Run `get_coupling_metrics` on a single-file package and show the degenerate case."
  - Chaining: "Use `get_coupling_metrics` to find fan-in hot spots, then `find_references` for detail."
- `get_module_dependencies`:
  - Goal: "Run `get_module_dependencies` on a module and return only first-party imports."
  - Validation: "Run `get_module_dependencies` on a syntactically broken module and show the parse-error envelope."
  - Chaining: "Use `get_module_dependencies`, then `check_layer_violations` to flag illegal edges."
- `get_module_public_api`:
  - Goal: "Run `get_module_public_api` and return only names exported via `__all__` or re-exports."
  - Validation: "Run `get_module_public_api` on a private module and confirm empty-API response."
  - Chaining: "Use `get_module_public_api`, then `find_references` cross-repo to size breakage for a rename."

#### Change history & previewing

- `diff_preview`:
  - Goal: "Run `diff_preview` on a pending TextEdit list and summarize top 3 hunks."
  - Validation: "Run `diff_preview` with an empty edit list and confirm the no-op response."
  - Chaining: "Pipe any refactor `apply=false` result into `diff_preview`; only apply if diff looks right."
- `begin_change_stack`:
  - Goal: "Run `begin_change_stack` and return the new stack id."
  - Validation: "Run `begin_change_stack` when one is already open and show the nested-stack rejection."
  - Chaining: "Call `begin_change_stack`, perform refactors, then `commit_change_stack` or `rollback_change_stack`."
- `commit_change_stack`:
  - Goal: "Run `commit_change_stack` and return a summary of files changed."
  - Validation: "Run `commit_change_stack` with no open stack and show the invalid-state error."
  - Chaining: "After `commit_change_stack`, call `get_diagnostics` on the touched file set."
- `rollback_change_stack`:
  - Goal: "Run `rollback_change_stack` and confirm the workspace matches the pre-stack state."
  - Validation: "Run `rollback_change_stack` after a commit and show the already-committed rejection."
  - Chaining: "If a post-apply `get_diagnostics` shows regressions, call `rollback_change_stack` and try a different refactor."
- `undo_refactoring`:
  - Goal: "Run `undo_refactoring` and return the reverted change id + files restored."
  - Validation: "Run `undo_refactoring` with an empty history and show the no-history response."
  - Chaining: "Pair `undo_refactoring` with `get_refactoring_history` to pick the correct revert target."
- `redo_refactoring`:
  - Goal: "Run `redo_refactoring` and return the reapplied change id."
  - Validation: "Run `redo_refactoring` with nothing to redo and show the empty-redo response."
  - Chaining: "Use `undo_refactoring`, inspect diagnostics, then `redo_refactoring` if the revert was wrong."
- `get_refactoring_history`:
  - Goal: "Run `get_refactoring_history` and return the last 10 change entries with timestamp + tool."
  - Validation: "Run `get_refactoring_history` on a fresh session and confirm the empty list."
  - Chaining: "Use `get_refactoring_history` to audit recent edits, then `undo_refactoring` selectively."

#### Infrastructure

- `list_environments`:
  - Goal: "Run `list_environments` and return the resolved interpreter path for the primary workspace."
  - Validation: "Run `list_environments` in an environment with no venv and confirm the fallback interpreter entry."
  - Chaining: "Use `list_environments` output to decide whether to call `create_type_stubs`."
- `restart_server`:
  - Goal: "Run `restart_server` and confirm the Pyright LSP lifecycle restarts cleanly."
  - Validation: "Run `restart_server` mid-refactor and show the queued-operation rejection."
  - Chaining: "After `restart_server`, call `get_workspace_diagnostics` to re-seed analysis state."
- `create_type_stubs`:
  - Goal: "Run `create_type_stubs` for a third-party package and return the generated `.pyi` path."
  - Validation: "Run `create_type_stubs` on a package already shipping stubs and confirm no-op."
  - Chaining: "Generate with `create_type_stubs`, then `get_type_coverage` to confirm improvement."

## F. Prioritization Rubric

Score each new tool from 1-5 in each category:
- Agent utility (frequency + impact)
- Safety risk (lower risk = higher score)
- Implementation complexity (lower complexity = higher score)
- Testability and determinism
- Chainability with existing tools

Implement highest total first; defer low-testability/high-risk tools.
