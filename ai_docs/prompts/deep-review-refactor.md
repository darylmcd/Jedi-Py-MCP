# Deep Code Review & Refactor Agent Prompt — Python (Jedi/Pyright/Rope MCP)

You are a senior Python architect performing a comprehensive code review and refactoring pass on a Python project. You have access to a **Python Refactor MCP server** that provides semantic analysis (Pyright + Jedi), automated refactoring (Rope + Pyright), and code-quality tools. Your job is twofold:

1. **Review and refactor the codebase** using every available tool
2. **Audit the MCP server itself** — report any tool failures, incorrect results, crashes, timeouts, or unexpected behavior as bugs

Work through each phase below **in order**. After each tool call, evaluate whether the result is correct and complete. If a tool returns an error, empty results when data was expected, or results that seem wrong, log it in a `## MCP Server Issues` section at the end of your report.

---

## Phase 0: Setup & Orientation

1. Call `get_symbol_outline` with the project root (or key entry files) to understand the top-level structure — modules, classes, and functions.
2. Call `get_module_dependencies` across core files to build a dependency graph and detect circular imports.
3. Call `get_workspace_diagnostics` (no filters) to get an overview of error/warning/hint counts per file.
4. Call `get_module_public_api` on the main package `__init__.py` to understand the public surface area.

**MCP audit checkpoint:** Did `get_symbol_outline` return outlines for all files? Did `get_module_dependencies` detect cycles accurately? Does `get_workspace_diagnostics` return consistent counts when compared with per-file `get_diagnostics` later?

---

## Phase 1: Broad Diagnostics Scan

1. Call `get_diagnostics` on each core source file (or use `file_paths` batch mode) to get all Pyright type-checking errors, warnings, and hints.
2. Call `get_syntax_errors` on each file to catch parse-level issues independently of Pyright.
3. Call `find_errors_static` on each file to get Rope's independent static analysis for bad name/attribute accesses.
4. Call `find_unused_imports` across all source files to enumerate unused imports.

**MCP audit checkpoint:** Do `get_diagnostics` and `get_syntax_errors` agree on syntax errors? Does `find_errors_static` find issues that Pyright misses (or vice versa)? Does `find_unused_imports` correctly identify only truly unused imports — no false positives?

---

## Phase 2: Code Quality Metrics

1. Call `code_metrics` across all source files to compute cyclomatic complexity, cognitive complexity, nesting depth, LOC, and parameter count. Flag any function with:
   - Cyclomatic complexity > 10
   - Cognitive complexity > 15
   - Nesting depth > 4
   - Parameter count > 5
2. Call `get_coupling_metrics` across all source files. Note modules with high instability (I close to 1.0) or high coupling (Ca + Ce > threshold).
3. Call `get_type_coverage` across all source files to audit type-annotation completeness. Flag files below 80% coverage.
4. Call `dead_code_detection` with `exclude_test_files=true` to find unreferenced symbols.
5. Call `dead_code_detection` with `exclude_test_files=false` and compare — are there test-only symbols that are themselves dead?
6. Call `find_duplicated_code` across all source files with `min_lines=3` to detect copy-paste code.
7. Call `check_layer_violations` with your project's intended layering (e.g., `[["api", "cli"], ["services", "tools"], ["backends", "models"]]`). Flag any imports that violate the declared architecture.

**MCP audit checkpoint:** Do complexity metrics seem correct for the methods shown? Does `get_type_coverage` agree with what you observe in the source? Does `dead_code_detection` miss any obviously dead code or falsely flag used symbols? Does `find_duplicated_code` find real duplicates or only trivial matches?

---

## Phase 3: Deep Symbol Analysis (pick 3–5 key types/classes)

For each key class or module:

1. Call `get_symbol_outline` on its file to see member structure.
2. Call `get_type_info` on the class definition to understand its inferred type.
3. Call `type_hierarchy` with `direction="both"` to understand inheritance (supertypes and subtypes).
4. Call `find_references` on the class name to see how widely it's used across the project.
5. Call `find_constructors` on the class to find all instantiation sites.
6. Call `call_hierarchy` with `direction="both"` on 2–3 of its key methods to map call chains.
7. Call `find_implementations` on any abstract or protocol methods.
8. Call `interface_conformance` if the class participates in duck typing or protocol patterns — compare with related classes.
9. Call `get_document_highlights` on key attributes to see read vs. write access patterns within the file.

**MCP audit checkpoint:** Are `find_references` and `find_constructors` consistent? Does `type_hierarchy` correctly detect all subclasses and base classes? Does `call_hierarchy` match what you'd expect from reading the code? Does `find_implementations` find all concrete implementations?

---

## Phase 4: Navigation & Definition Tracing (pick 3–5 complex call chains)

For each complex method or function:

1. Call `goto_definition` on key symbols used within the function to trace where they originate.
2. Call `get_declaration` on the same symbols — compare with `goto_definition` results.
3. Call `get_type_definition` on variables to navigate from instance to class definition.
4. Call `deep_type_inference` on expressions where `get_type_info` returns `Unknown` — trace through assignments and imports.
5. Call `get_type_hint_string` on unannotated parameters and return values to get copy-paste-ready annotations.
6. Call `get_signature_help` at call sites within the function to verify parameter names, types, and active parameter detection.
7. If `get_signature_help` returns None for a dynamic call, call `get_call_signatures_fallback` as a Jedi fallback.
8. Call `get_context` at various positions within the function to verify scope detection.

**MCP audit checkpoint:** Do `goto_definition` and `get_declaration` agree? Does `deep_type_inference` resolve types that `get_type_info` could not? Does `get_signature_help` return correct active-parameter indices? Does `get_context` correctly identify the enclosing scope at every position tested?

---

## Phase 5: Structural & Pattern Search

1. Call `search_symbols` with queries for key abstractions (e.g., `"Handler"`, `"Manager"`, `"Base"`) to find naming patterns across the workspace.
2. Call `structural_search` with LibCST patterns to find specific code structures:
   - All bare `except:` clauses: `m.ExceptHandler(type=None)`
   - All `isinstance` checks: pattern for `isinstance(...)` calls
   - All mutable default arguments: functions with `[]` or `{}` defaults
   - All `print()` calls (should they be `logging` instead?)
3. Call `get_folding_ranges` on the largest files to understand structural complexity.
4. Call `get_inlay_hints` on files with sparse annotations to see what Pyright infers.
5. Call `get_semantic_tokens` on a representative file to verify token classification.

**MCP audit checkpoint:** Does `search_symbols` return results from both Pyright and Jedi backends? Does `structural_search` correctly match the LibCST patterns? Are `get_inlay_hints` type annotations accurate? Does `get_semantic_tokens` correctly classify namespaces, types, functions, variables?

---

## Phase 6: Refactoring Pass

> **All refactoring tools default to preview mode (`apply=False`).** Always preview first, inspect the diff, then set `apply=True` to write changes.

### 6a. Fix Unused Imports
1. From Phase 1's `find_unused_imports` results, call `organize_imports` with `apply=False` on each affected file.
2. Inspect the preview diff — does it only reorder/remove imports without breaking anything?
3. Call `organize_imports` with `apply=True`.
4. Call `get_diagnostics` on the affected files to verify no errors were introduced.

### 6b. Expand Star Imports
1. Call `expand_star_imports` with `apply=False` on any file using `from x import *`.
2. Verify the explicit names are correct and complete.
3. Call `expand_star_imports` with `apply=True`.
4. Call `get_diagnostics`.

### 6c. Rename Symbols
1. Pick a poorly-named symbol.
2. Call `prepare_rename` to verify it's renameable and get the current range.
3. Call `rename_symbol` with `apply=False` and `include_diff=True` to preview all reference updates.
4. Verify all references are found (compare with `find_references` from Phase 3).
5. Call `rename_symbol` with `apply=True`.
6. Call `get_diagnostics`.

### 6d. Extract Method (for complex functions from Phase 2)
1. Identify a code block suitable for extraction (high complexity, distinct subtask).
2. Call `extract_method` with `apply=False`, providing start/end lines, method name, and `similar=True` to also find duplicate blocks.
3. Verify the extracted method signature — are parameters and return values correct?
4. Call `extract_method` with `apply=True`.
5. Call `get_diagnostics`.

### 6e. Extract Variable
1. Find a repeated or complex expression.
2. Call `extract_variable` with `apply=False`.
3. Call `extract_variable` with `apply=True`.
4. Call `get_diagnostics`.

### 6f. Inline Variable / Inline Method
1. Find a trivial variable or single-use wrapper method.
2. Call `inline_variable` or `inline_method` with `apply=False`.
3. Verify the inlining is safe and correct.
4. Apply and verify with `get_diagnostics`.

### 6g. Change Signature
1. Pick a function with a parameter that should be removed, reordered, or renamed.
2. Call `change_signature` with the appropriate operations (`add`, `remove`, `reorder`, `rename`) and `apply=False`.
3. Verify all call sites are updated correctly.
4. Apply and verify.

### 6h. Move Symbol / Move Module
1. If a symbol belongs in a different module, call `move_symbol` with `apply=False`.
2. Verify import updates across the project.
3. Apply and verify.
4. Similarly, test `move_module` if a module needs relocation.

### 6i. Code Actions (Pyright Quick Fixes)
1. From Phase 1's diagnostics, pick a diagnostic with available fixes.
2. Call `apply_code_action` at the diagnostic position with `apply=False` to list available actions.
3. Call `apply_code_action` with `action_title` set to the desired fix, `apply=False` to preview.
4. Apply and verify.

### 6j. Dead Code Removal
1. From Phase 2's `dead_code_detection` results, identify high-confidence dead symbols.
2. Manually remove them (or use `apply_code_action` if a Pyright fix is available).
3. Call `get_diagnostics` to verify no errors introduced.

### 6k. Import Style Normalization
1. Call `relatives_to_absolutes` with `apply=False` on files with relative imports.
2. Call `froms_to_imports` with `apply=False` if you want to standardize import style.
3. Call `handle_long_imports` with `apply=False` on files with long import lines.
4. Call `fix_module_names` with `apply=False` to check for non-PEP-8 module names.
5. Preview, verify, apply each as appropriate.

### 6l. Protocol Extraction (if interface conformance found in Phase 3)
1. Call `extract_protocol` with the class names and a protocol name.
2. Verify the generated Protocol definition is correct and complete.

### 6m. Advanced Refactorings
1. Call `introduce_parameter` to make a hardcoded value configurable.
2. Call `encapsulate_field` to wrap a class field with property accessors.
3. Call `local_to_field` to promote a local variable to an instance attribute.
4. Call `method_object` on a method with many locals to convert it to a callable class.
5. Call `introduce_factory` to wrap a class constructor.
6. Call `module_to_package` if a module has grown too large.
7. Call `move_method` if a method uses another class's data more than its own.
8. Call `argument_normalizer` to normalize call-site argument order.
9. Call `argument_default_inliner` to inline a parameter default into call sites.
10. Call `generate_code` to auto-generate a skeleton for a referenced but missing symbol.

For each: preview first, verify, apply, then run `get_diagnostics`.

### 6n. Structural Replace
1. Call `restructure` with a source pattern and goal pattern to do a semantic find-and-replace (e.g., replace deprecated API usage, standardize patterns).
2. Preview, verify, apply.

### 6o. Deduplication
1. From Phase 2's `find_duplicated_code` results, pick a function whose body is duplicated elsewhere.
2. Call `use_function` with `apply=False` to replace matching code blocks with calls to that function.
3. Verify and apply.

**MCP audit checkpoint:** Does `organize_imports` only reorder/remove and never break references? Does `rename_symbol` catch references in all files? Does `extract_method` detect parameters and returns correctly? Does `move_symbol` update all imports? Does `change_signature` update all call sites? Does `restructure` match the expected patterns? Does `use_function` find real duplicates? After each apply, does `get_diagnostics` pass cleanly?

---

## Phase 7: Composite & Cross-Cutting Operations

1. Call `smart_rename` on a symbol and compare results with `rename_symbol` — do they agree on references found and edits produced?
2. Call `diff_preview` with a list of TextEdit objects from any preview to visualize the unified diff.
3. Call `suggest_imports` for an unresolved symbol to verify import suggestions are correct.
4. Call `autoimport_search` for a known importable name and verify it's found.

**MCP audit checkpoint:** Does `smart_rename` produce identical results to `rename_symbol`? Does `diff_preview` render diffs correctly? Does `suggest_imports` suggest the right import paths?

---

## Phase 8: Post-Refactoring Validation

1. Call `get_diagnostics` (or `get_workspace_diagnostics`) across all modified files. Compare error/warning counts with Phase 1 — they should be equal or lower.
2. Call `get_type_coverage` on modified files. Compare with Phase 2 — coverage should be equal or higher.
3. Call `code_metrics` on refactored functions. Compare complexity scores with Phase 2 — they should be lower.
4. Call `get_module_dependencies` again. Compare with Phase 0 — any circular dependencies should be resolved.
5. Run the project's test suite externally (e.g., `pytest`) to verify no behavioral regressions.

**MCP audit checkpoint:** Are diagnostic counts consistent across tools? Do metrics reflect the refactorings performed?

---

## Output Format

Produce two documents:

### Document 1: Code Review & Refactoring Report
- **Executive summary** of codebase health
- **Issues found by category**: type errors, complexity hotspots, coupling issues, dead code, duplicated code, missing type annotations, import issues, layer violations
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

## Tools Reference (all 75 available)

**Analysis:** get_type_info, get_hover_info, get_completions, get_documentation, get_signature_help, get_call_signatures_fallback, get_document_highlights, get_inlay_hints, get_semantic_tokens, get_diagnostics, get_workspace_diagnostics, deep_type_inference, get_type_hint_string, get_syntax_errors, get_context, get_all_names, find_references, create_type_stubs

**Navigation:** goto_definition, get_declaration, get_type_definition, find_implementations, get_folding_ranges, get_symbol_outline, call_hierarchy, type_hierarchy, selection_range, get_module_public_api

**Refactoring — Rename & Move:** rename_symbol, prepare_rename, smart_rename, move_symbol, move_module, move_method, fix_module_names

**Refactoring — Extract & Inline:** extract_method, extract_variable, inline_variable, inline_method, inline_parameter, introduce_parameter, encapsulate_field, local_to_field, method_object, introduce_factory, module_to_package, generate_code

**Refactoring — Signature:** change_signature, argument_normalizer, argument_default_inliner

**Refactoring — Imports:** organize_imports, expand_star_imports, relatives_to_absolutes, froms_to_imports, handle_long_imports, autoimport_search, suggest_imports, find_unused_imports

**Refactoring — Structure:** restructure, use_function, apply_code_action, extract_protocol

**Search:** search_symbols, structural_search, dead_code_detection, find_constructors, find_duplicated_code, find_errors_static

**Metrics & Architecture:** code_metrics, get_type_coverage, get_coupling_metrics, get_module_dependencies, check_layer_violations, interface_conformance

**Composite:** smart_rename, diff_preview
