# Deep Code Review & Refactor Agent Prompt — Python (Jedi/Pyright/Rope MCP)
<!-- purpose: Reusable deep review prompt for exercising the full Python refactor MCP tool surface. -->

<!-- KEEP THIS FILE: This is a reusable prompt template. Update it when tools are added or removed. Do not delete — always keep in sync with the current tool surface in server.py. -->

You are a senior Python architect performing a comprehensive code review and refactoring pass on a Python project. You have access to a **Python Refactor MCP server** (88 tools) that provides semantic analysis (Pyright + Jedi), automated refactoring (Rope + Pyright), and code-quality tools. Your job is twofold:

1. **Review and refactor the codebase** using every available tool
2. **Audit the MCP server itself** — report any tool failures, incorrect results, crashes, timeouts, or unexpected behavior as bugs

Work through each phase below **in order**. After each tool call, evaluate whether the result is correct and complete. If a tool returns an error, empty results when data was expected, or results that seem wrong, log it in a `## MCP Server Issues` section at the end of your report.

---

## Phase 0: Setup & Orientation

1. `get_symbol_outline` with the project root (or key entry files) to understand top-level structure — modules, classes, and functions.
2. `get_module_dependencies` across core files to build a dependency graph and detect circular imports.
3. `get_workspace_diagnostics` (no filters) for error/warning/hint counts per file.
4. `get_module_public_api` on the main package `__init__.py` to understand the public surface area.
5. `list_environments` to discover available Python environments and virtualenvs.

**MCP audit checkpoint:** Did `get_symbol_outline` return outlines for all files? Did `get_module_dependencies` detect cycles accurately? Does `get_workspace_diagnostics` return consistent counts when compared with per-file `get_diagnostics` later? Did `list_environments` detect the active environment correctly?

---

## Phase 1: Broad Diagnostics Scan

1. `get_diagnostics` on each core source file (or use `file_paths` batch mode) to get all Pyright type-checking errors, warnings, and hints. Use `suppress_codes` to filter noise if needed.
2. `get_syntax_errors` on each file to catch parse-level issues independently of Pyright.
3. `find_errors_static` on each file for Rope's independent static analysis of bad name/attribute accesses.
4. `find_unused_imports` across all source files to enumerate unused imports.

**MCP audit checkpoint:** Do `get_diagnostics` and `get_syntax_errors` agree on syntax errors? Does `find_errors_static` find issues that Pyright misses (or vice versa)? Does `find_unused_imports` correctly identify only truly unused imports — no false positives on `__future__` or re-exports?

---

## Phase 2: Code Quality & Security Metrics

1. `code_metrics` across all source files to compute cyclomatic complexity, cognitive complexity, nesting depth, LOC, and parameter count. Flag any function with:
   - Cyclomatic complexity > 10
   - Cognitive complexity > 15
   - Nesting depth > 4
   - Parameter count > 5
2. `get_coupling_metrics` across all source files. Note modules with high instability (I close to 1.0) or high coupling (Ca + Ce > threshold).
3. `get_type_coverage` across all source files to audit type-annotation completeness. Flag files below 80% coverage.
4. `dead_code_detection` with `exclude_test_files=true` to find unreferenced symbols. Use `offset`/`limit` for pagination on large codebases.
5. `dead_code_detection` with `exclude_test_files=false` and compare — are there test-only symbols that are themselves dead?
6. `find_duplicated_code` across all source files with `min_lines=3` to detect copy-paste code.
7. `check_layer_violations` with your project's intended layering (e.g., `[["api", "cli"], ["services", "tools"], ["backends", "models"]]`). Flag any imports that violate the declared architecture.
8. `security_scan` across all source files to detect common Python vulnerabilities (eval, exec, shell injection, pickle, etc.).
9. `get_test_coverage_map` across source files to see which functions/classes have test references and which are untested.

**MCP audit checkpoint:** Do complexity metrics seem correct for the methods shown? Does `get_type_coverage` agree with what you observe in the source? Does `dead_code_detection` miss any obviously dead code or falsely flag decorated/`__all__` symbols? Does `find_duplicated_code` find real duplicates or only trivial matches? Does `security_scan` find real issues without excessive false positives? Does `get_test_coverage_map` accurately map tests to source symbols?

---

## Phase 3: Deep Symbol Analysis (pick 3-5 key types/classes)

For each key class or module:

1. `get_symbol_outline` on its file to see member structure.
2. `get_type_info` on the class definition to understand its inferred type.
3. `type_hierarchy` with `direction="both"` to understand inheritance (supertypes and subtypes). Use `class_name` if the position is ambiguous.
4. `find_references` on the class name to see how widely it's used across the project. Use `include_context=true` for surrounding source lines.
5. `find_constructors` on the class to find all instantiation sites.
6. `call_hierarchy` with `direction="both"` on 2-3 of its key methods to map call chains. Increase `depth` for deeper traversal.
7. `find_implementations` on any abstract or protocol methods.
8. `interface_conformance` if the class participates in duck typing or protocol patterns — compare with related classes.
9. `extract_protocol` if conformance analysis reveals shared interfaces worth formalizing.
10. `get_document_highlights` on key attributes to see read vs. write access patterns within the file.
11. `get_sub_definitions` on key class references to list their methods and members via Jedi.

**MCP audit checkpoint:** Are `find_references` and `find_constructors` consistent? Does `type_hierarchy` correctly detect all subclasses and base classes (non-empty name field)? Does `call_hierarchy` match what you'd expect from reading the code? Does `find_implementations` find all concrete implementations? Does `get_sub_definitions` return the expected members?

---

## Phase 4: Navigation & Definition Tracing (pick 3-5 complex call chains)

For each complex method or function:

1. `goto_definition` on key symbols used within the function to trace where they originate.
2. `get_declaration` on the same symbols — compare with `goto_definition` results.
3. `get_type_definition` on variables to navigate from instance to class definition.
4. `deep_type_inference` on expressions where `get_type_info` returns `Unknown` — trace through assignments and imports.
5. `get_type_hint_string` on unannotated parameters and return values to get copy-paste-ready annotations.
6. `get_signature_help` at call sites within the function to verify parameter names, types, and active parameter detection.
7. `simulate_execution` on callable references to check inferred return types via Jedi's execution simulation.
8. `get_context` at various positions within the function to verify scope detection.
9. `get_documentation` on key symbols to review docstring completeness and accuracy. Use the `source` parameter for in-memory analysis if needed.
10. `get_keyword_help` on Python keywords and operators (e.g., `yield`, `async`, `with`) to verify keyword documentation works correctly.
11. `get_all_names` with `references=true` to audit all names used in a file and discover unexpected scope leaks.

**MCP audit checkpoint:** Do `goto_definition` and `get_declaration` agree? Does `deep_type_inference` resolve types that `get_type_info` could not? Does `get_signature_help` return correct active-parameter indices? Does `get_context` correctly identify the enclosing scope at every position tested? Does `simulate_execution` return reasonable result types? Does `get_keyword_help` return documentation for keywords?

---

## Phase 5: Structural & Pattern Search

1. `search_symbols` with queries for key abstractions (e.g., `"Handler"`, `"Manager"`, `"Base"`) to find naming patterns across the workspace.
2. `project_search` with the same queries to compare Jedi's semantic search results. Set `complete=True` for completion-style search.
3. `structural_search` with LibCST patterns to find specific code structures:
   - All bare `except:` clauses: `m.ExceptHandler(type=None)`
   - All `isinstance` checks: pattern for `isinstance(...)` calls
   - All mutable default arguments: functions with `[]` or `{}` defaults
   - All `print()` calls (should they be `logging` instead?)
   - Check `files_scanned` in the response to distinguish "found nothing" from "failed to scan"
4. `get_folding_ranges` on the largest files to understand structural complexity.
5. `get_inlay_hints` on files with sparse annotations to see what Pyright infers.
6. `get_semantic_tokens` on a representative file to verify token classification. Use `limit` to cap output size.
7. `get_completions` at a few positions to verify completion quality and relevance.
8. `selection_range` at key positions to verify nested scope detection for extraction candidates.

**MCP audit checkpoint:** Does `search_symbols` return results from both Pyright and Jedi backends? Does `project_search` find symbols that `search_symbols` misses (or vice versa)? Does `structural_search` correctly match the LibCST patterns and report `files_scanned`? Are `get_inlay_hints` type annotations accurate? Does `get_semantic_tokens` correctly classify namespaces, types, functions, variables?

---

## Phase 6: Refactoring Pass

> **All refactoring tools default to preview mode (`apply=False`).** Always preview first, inspect the diff, then set `apply=True` to write changes.
>
> **Atomic change stacks:** For multi-step refactorings that must succeed or fail together, wrap them in a change stack:
> 1. `begin_change_stack` to start.
> 2. Apply multiple refactorings with `apply=True`.
> 3. `commit_change_stack` to apply all atomically, or `rollback_change_stack` to discard.

### 6a. Fix Unused Imports
1. From Phase 1's `find_unused_imports` results, call `organize_imports` with `apply=False` on each affected file.
2. Inspect the preview diff — does it only reorder/remove imports without breaking anything?
3. `organize_imports` with `apply=True`.
4. `get_diagnostics` on the affected files to verify no errors were introduced.

### 6b. Expand Star Imports
1. `expand_star_imports` with `apply=False` on any file using `from x import *`.
2. Verify the explicit names are correct and complete.
3. `expand_star_imports` with `apply=True`.
4. `get_diagnostics`.

### 6c. Rename Symbols
1. Pick a poorly-named symbol.
2. `prepare_rename` to verify it's renameable and get the current range.
3. `rename_symbol` with `apply=False` and `include_diff=True` to preview all reference updates.
4. Verify all references are found (compare with `find_references` from Phase 3).
5. `rename_symbol` with `apply=True`.
6. `get_diagnostics`.

### 6d. Multi-Project Rename
1. If the symbol is used across multiple workspace roots, use `multi_project_rename` with `additional_roots` listing the other project directories.
2. Preview with `apply=False`, verify cross-project reference updates.
3. Apply and verify.

### 6e. Extract Method (for complex functions from Phase 2)
1. Identify a code block suitable for extraction (high complexity, distinct subtask).
2. `extract_method` with `apply=False`, providing start/end lines, method name, and `similar=True` to also find duplicate blocks.
3. Verify the extracted method signature — are parameters and return values correct?
4. `extract_method` with `apply=True`.
5. `get_diagnostics`.

### 6f. Extract Variable
1. Find a repeated or complex expression.
2. `extract_variable` with `apply=False`.
3. `extract_variable` with `apply=True`.
4. `get_diagnostics`.

### 6g. Inline Variable / Inline Method
1. Find a trivial variable or single-use wrapper method.
2. `inline_variable` or `inline_method` with `apply=False`.
3. Verify the inlining is safe and correct.
4. Apply and verify with `get_diagnostics`.

### 6h. Inline Parameter
1. Find a parameter that is always called with the same value.
2. `inline_parameter` with `apply=False` — cursor on the parameter name in the function definition.
3. Verify the default is inlined into the function body correctly.
4. Apply and verify.

### 6i. Change Signature
1. Pick a function with a parameter that should be removed, reordered, or renamed.
2. `change_signature` with the appropriate operations (`add`, `remove`, `reorder`, `rename`, `inline_default`, `normalize`) and `apply=False`.
3. Verify all call sites are updated correctly.
4. Apply and verify.
5. **Known limitation:** Rope's `ArgumentNormalizer` strips Python 3 type annotations. Verify annotations are preserved after applying.

### 6j. Argument Normalization
1. Find functions where call sites pass keyword arguments in a different order than the signature.
2. `argument_normalizer` with `apply=False` to preview reordering.
3. Apply and verify.

### 6k. Argument Default Inlining
1. Find a parameter with a default value that should be pushed to all call sites.
2. `argument_default_inliner` with the 0-based parameter `index` and `apply=False`.
3. Verify the default is inlined at all call sites that omit it.
4. Apply and verify.

### 6l. Move Symbol / Move Module / Move Method
1. If a symbol belongs in a different module, call `move_symbol` with `apply=False`.
2. Verify import updates across the project.
3. Apply and verify.
4. Similarly, test `move_module` for module relocation and `move_method` for moving a method to another class (specify `destination_attr`).

### 6m. Code Actions (Pyright Quick Fixes)
1. From Phase 1's diagnostics, pick a diagnostic with available fixes.
2. `apply_code_action` at the diagnostic position with `apply=False` to list available actions.
3. `apply_code_action` with `action_title` set to the desired fix, `apply=False` to preview.
4. Apply and verify.

### 6n. Dead Code Removal
1. From Phase 2's `dead_code_detection` results, identify high-confidence dead symbols.
2. Manually remove them (or use `apply_code_action` if a Pyright fix is available).
3. `get_diagnostics` to verify no errors introduced.

### 6o. Import Style Normalization
1. `relatives_to_absolutes` with `apply=False` on files with relative imports.
2. `froms_to_imports` with `apply=False` if you want to standardize import style.
3. `handle_long_imports` with `apply=False` on files with long import lines.
4. `fix_module_names` with `apply=False` to check for non-PEP-8 module names.
5. Preview, verify, apply each as appropriate.

### 6p. Protocol Extraction (if interface conformance found in Phase 3)
1. `extract_protocol` with the class names and a protocol name.
2. Verify the generated Protocol definition is correct and complete.

### 6q. Advanced Refactorings
1. `introduce_parameter` to make a hardcoded value configurable. Specify `parameter_name` and optional `default_value`.
2. `encapsulate_field` to wrap a class field with property accessors.
3. `local_to_field` to promote a local variable to an instance attribute.
4. `method_object` on a method with many locals to convert it to a callable class. Optionally specify `classname`.
5. `introduce_factory` to wrap a class constructor. Optionally specify `factory_name` and `global_factory`.
6. `module_to_package` if a module has grown too large.
7. `generate_code` to auto-generate a skeleton for a referenced but missing symbol (specify `kind`: class/function/variable/module/package).

For each: preview first, verify, apply, then run `get_diagnostics`.

### 6r. Structural Replace
1. `restructure` with a source `pattern` and `goal` pattern to do a semantic find-and-replace (e.g., replace deprecated API usage, standardize patterns). Use `checks` to constrain matches and `imports` to add needed imports.
2. Preview, verify, apply.

### 6s. Deduplication
1. From Phase 2's `find_duplicated_code` results, pick a function whose body is duplicated elsewhere.
2. `use_function` with `apply=False` to replace matching code blocks with calls to that function.
3. Verify and apply.

### 6t. Type Stub Generation
1. If any third-party package lacks type information, call `create_type_stubs` with the package name.
2. Optionally specify `output_dir` for custom stub location.

**MCP audit checkpoint:** Does `organize_imports` only reorder/remove and never break references? Does `rename_symbol` catch references in all files? Does `multi_project_rename` correctly update cross-project references? Does `extract_method` detect parameters and returns correctly? Does `move_symbol` update all imports? Does `change_signature` update all call sites (and preserve type annotations)? Does `restructure` match the expected patterns? Does `use_function` find real duplicates? Do change stacks commit/rollback atomically? After each apply, does `get_diagnostics` pass cleanly?

---

## Phase 7: Cross-Cutting Operations & History

1. `diff_preview` with a list of TextEdit objects from any preview to visualize the unified diff.
2. `suggest_imports` for an unresolved symbol to verify import suggestions are correct.
3. `autoimport_search` for a known importable name and verify it's found (graceful empty list on failure).
4. `get_refactoring_history` to review the history of all refactoring operations performed in this session.
5. `undo_refactoring` on the most recent refactoring to test undo capability, then `redo_refactoring` to restore it.
6. `restart_server` to discard Pyright's cached type info and restart analysis. Verify diagnostics refresh correctly afterward.

**MCP audit checkpoint:** Does `diff_preview` render diffs correctly? Does `suggest_imports` suggest the right import paths? Does `autoimport_search` return results without crashing? Does `get_refactoring_history` accurately list all operations? Does `undo_refactoring`/`redo_refactoring` correctly reverse and restore changes? Does `restart_server` resolve stale diagnostic issues?

---

## Phase 8: Post-Refactoring Validation

1. `get_diagnostics` (or `get_workspace_diagnostics`) across all modified files. Compare error/warning counts with Phase 1 — they should be equal or lower.
2. `get_type_coverage` on modified files. Compare with Phase 2 — coverage should be equal or higher.
3. `code_metrics` on refactored functions. Compare complexity scores with Phase 2 — they should be lower.
4. `get_module_dependencies` again. Compare with Phase 0 — any circular dependencies should be resolved.
5. `security_scan` on modified files. Compare with Phase 2 — no new vulnerabilities should be introduced.
6. `get_test_coverage_map` on modified files. Verify test mappings still hold after refactoring.
7. Run the project's test suite externally (e.g., `pytest`) to verify no behavioral regressions.

**MCP audit checkpoint:** Are diagnostic counts consistent across tools? Do metrics reflect the refactorings performed? Are diagnostics fresh (not stale from cache)?

---

## Output Format

Produce two documents:

### Document 1: Code Review & Refactoring Report
- **Executive summary** of codebase health
- **Issues found by category**: type errors, complexity hotspots, coupling issues, dead code, duplicated code, missing type annotations, import issues, layer violations, security vulnerabilities, untested code
- **Refactorings performed** and their impact (with before/after metrics)
- **Remaining items** that need manual attention
- **Metrics comparison table**: diagnostic counts, complexity scores, type coverage, coupling metrics — before and after

### Document 2: MCP Server Audit Report
For each issue found, include:
- **Tool name** that exhibited the issue
- **Input parameters** that triggered it
- **Expected behavior** vs **actual behavior**
- **Severity**: crash / incorrect result / missing data / degraded performance / cosmetic
- **Reproducibility**: always / sometimes / once

Categories:
- Tool crashes or unhandled exceptions
- Incorrect or incomplete results
- Inconsistencies between tools that should agree (e.g., `find_references` vs `rename_symbol` reference counts)
- Missing functionality or edge cases not handled
- Performance issues (tools that take unreasonably long)
- Serialization issues (malformed output, truncated results)
- Line number or position mapping errors (0-based vs 1-based mismatches)
- Backend disagreements (Pyright vs Jedi vs Rope returning conflicting data)

---

## Tools Reference (91 available)

### Analysis (21 tools)
`find_references(file_path, line, character, include_declaration=True, include_context=False, limit=None)` — All references to a symbol across the workspace
`find_type_users(file_path, line, character, kinds=None, include_declaration=False, limit=None)` — Inverse of `find_references` scoped to a type — classify sites as annotation / instantiation / subclass / other
`get_type_info(file_path, line, character)` — Infer type of a symbol or expression
`get_completions(file_path, line, character, fuzzy=False, limit=None)` — Code completion candidates
`get_documentation(file_path, line, character, source=None)` — Detailed docs and docstrings (Jedi)
`get_keyword_help(file_path, line, character)` — Documentation for Python keywords and operators (Jedi)
`get_signature_help(file_path, line, character)` — Function signature at a call site
`get_document_highlights(file_path, line, character)` — Read/write accesses within a file
`get_inlay_hints(file_path, start_line=0, start_character=0, end_line=None, end_character=0)` — Inline type annotations and parameter names
`get_semantic_tokens(file_path, limit=None)` — Semantic token classifications
`get_diagnostics(file_path=None, severity_filter=None, limit=None, suppress_codes=None, file_paths=None)` — Type-checking diagnostics
`get_workspace_diagnostics(root_path=None, suppress_codes=None, file_paths=None, offset=0, limit=None)` — Aggregated diagnostic counts per file
`deep_type_inference(file_path, line, character)` — Resolve final types through imports and assignments
`get_type_hint_string(file_path, line, character)` — Copy-paste-ready type annotation strings
`get_syntax_errors(file_path)` — Jedi parser syntax errors
`get_context(file_path, line, character)` — Enclosing scope at a position
`get_all_names(file_path, all_scopes=True, references=False)` — All defined names in a file
`get_sub_definitions(file_path, line, character)` — Sub-definitions of a name (e.g., methods of a class). Uses Jedi
`simulate_execution(file_path, line, character)` — Simulate calling a callable and return result types (Jedi)
`create_type_stubs(package_name, output_dir=None)` — Generate .pyi stubs for untyped packages
`list_environments()` — Discover Python environments and virtualenvs (Jedi)

### Navigation (10 tools)
`goto_definition(file_path, line, character)` — Jump to symbol definition
`get_declaration(file_path, line, character)` — Navigate to declaration site
`get_type_definition(file_path, line, character)` — Navigate to type definition (instance → class)
`find_implementations(file_path, line, character)` — Concrete implementations of abstract/protocol methods
`get_folding_ranges(file_path)` — Foldable code regions
`get_symbol_outline(file_path=None, kind_filter=None, name_pattern=None, limit=None, root_path=None, file_paths=None, offset=0)` — Hierarchical symbol outline
`call_hierarchy(file_path, line, character, direction="both", depth=1, max_items=200)` — Callers and callees
`type_hierarchy(file_path, line, character, direction="both", depth=3, max_items=200, class_name=None)` — Class inheritance tree
`selection_range(file_path, positions)` — Nested selection ranges for smart expand/shrink
`get_module_public_api(file_path)` — Exported symbols from a module

### Refactoring — Rename & Move (7 tools)
`rename_symbol(file_path, line, character, new_name, apply=False, include_diff=False)` — Project-wide rename
`prepare_rename(file_path, line, character)` — Rename preflight check
`multi_project_rename(additional_roots, file_path, line, character, new_name, apply=False)` — Rename across multiple Rope projects
`move_symbol(source_file, symbol_name, destination_file, apply=False)` — Move symbol between files
`move_module(source_path, destination_package, apply=False)` — Move/rename module or package
`move_method(file_path, line, character, destination_attr, apply=False)` — Move method to another class
`fix_module_names(apply=False)` — Batch PEP 8 module renaming

### Refactoring — Extract & Inline (12 tools)
`extract_method(file_path, start_line, start_character, end_line, end_character, method_name, similar=False, apply=False)` — Extract code into new method
`extract_variable(file_path, start_line, start_character, end_line, end_character, variable_name, apply=False)` — Extract expression into variable
`inline_variable(file_path, line, character, apply=False)` — Replace variable with its value
`inline_method(file_path, line, character, apply=False)` — Inline function body at all call sites
`inline_parameter(file_path, line, character, apply=False)` — Inline parameter default into body
`introduce_parameter(file_path, line, character, parameter_name, default_value="", apply=False)` — Convert expression to parameter
`encapsulate_field(file_path, line, character, apply=False)` — Wrap field with property accessors
`local_to_field(file_path, line, character, apply=False)` — Promote local to instance field
`method_object(file_path, line, character, classname=None, apply=False)` — Convert method to callable class
`introduce_factory(file_path, line, character, factory_name=None, global_factory=True, apply=False)` — Wrap constructor with factory
`module_to_package(file_path, apply=False)` — Convert module to package
`generate_code(file_path, line, character, kind, apply=False)` — Generate skeleton for missing symbol

### Refactoring — Signature (3 tools)
`change_signature(file_path, line, character, operations, apply=False)` — Modify signature and update call sites
`argument_normalizer(file_path, line, character, apply=False)` — Normalize call-site argument order
`argument_default_inliner(file_path, line, character, index, apply=False)` — Inline default into call sites

### Refactoring — Imports & Formatting (11 tools)
`organize_imports(file_path, apply=False, file_paths=None)` — Sort/group imports per PEP 8
`format_code(file_path, apply=False, file_paths=None)` — Run ruff-format (respects project config)
`apply_lint_fixes(file_path, apply=False, file_paths=None, unsafe_fixes=False)` — Apply ruff `--fix` auto-fixes
`apply_type_annotations(file_path, apply=False, file_paths=None)` — Materialize Pyright-inferred type hints into real annotations
`expand_star_imports(file_path, apply=False)` — Replace `from x import *` with explicit names
`relatives_to_absolutes(file_path, apply=False)` — Convert relative to absolute imports
`froms_to_imports(file_path, apply=False)` — Convert `from x import y` to `import x` style
`handle_long_imports(file_path, apply=False)` — Break long import lines
`autoimport_search(name)` — Search importable names via rope AutoImport cache
`suggest_imports(symbol, file_path)` — Import suggestions for unresolved symbol
`find_unused_imports(file_path, file_paths=None)` — Find unused imports

### Refactoring — Structure (4 tools)
`restructure(pattern, goal, checks=None, imports=None, file_path=None, apply=False)` — Pattern-based code transformation
`use_function(file_path, line, character, apply=False)` — Replace duplicate code with function calls
`apply_code_action(file_path, line, character, action_title=None, apply=False)` — Apply Pyright quick fix
`extract_protocol(file_path, class_names, protocol_name="GeneratedProtocol")` — Generate Protocol from shared methods

### Refactoring — History & Change Stacks (6 tools)
`begin_change_stack()` — Start an atomic change stack for chaining multiple refactorings
`commit_change_stack()` — Commit and apply the current change stack atomically
`rollback_change_stack()` — Discard the current change stack without applying
`undo_refactoring(count=1)` — Undo the last N refactoring operations (Rope history)
`redo_refactoring(count=1)` — Redo previously undone refactoring operations (Rope history)
`get_refactoring_history()` — Get refactoring change history with descriptions, dates, and affected files

### Search (8 tools)
`find_constructors(class_name, file_path=None, limit=None)` — All instantiation sites for a class
`search_symbols(query, limit=None)` — Workspace-wide symbol search (Pyright + Jedi)
`project_search(query, complete=False)` — Project-wide semantic search (Jedi). Set complete=True for completion-style
`structural_search(pattern, file_path=None, language="python", limit=None)` — LibCST pattern search
`dead_code_detection(file_path=None, exclude_patterns=None, root_path=None, exclude_test_files=True, file_paths=None, offset=0, limit=None)` — Unreferenced symbols
`find_duplicated_code(file_path, file_paths=None, min_lines=3)` — Duplicate function bodies
`find_errors_static(file_path)` — Rope static analysis for bad accesses
`find_unused_imports(file_path, file_paths=None)` — Unused imports (also listed under imports)

### Metrics, Security & Architecture (9 tools)
`code_metrics(file_path, file_paths=None)` — Complexity, cognitive, nesting, LOC, params
`get_type_coverage(file_path, file_paths=None)` — Type annotation completeness
`get_coupling_metrics(file_paths=None)` — Afferent/efferent coupling and instability
`get_module_dependencies(file_path=None, file_paths=None)` — Import dependency graph with cycle detection
`check_layer_violations(layers, file_paths=None)` — Import direction violations
`interface_conformance(file_path, class_names)` — Compare class interfaces for protocol conformance
`get_module_public_api(file_path)` — Exported symbols (also listed under navigation)
`security_scan(file_path=None, file_paths=None)` — AST-based security scan for common Python vulnerabilities
`get_test_coverage_map(file_path=None, file_paths=None)` — Map source symbols to test references

### Composite & Server Management (2 tools)
`diff_preview(edits)` — Unified diff preview for TextEdit lists
`restart_server()` — Discard cached type info and restart Pyright analysis
