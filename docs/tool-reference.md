# Tool Reference

91 MCP tools organized by category.

## Analysis (17)

| Tool | Purpose | Returns |
|---|---|---|
| `find_references` | Find all references to a symbol. | `ReferenceResult` |
| `find_type_users` | Inverse of `find_references` scoped to a type — classify sites as annotation / instantiation / subclass / other. | `TypeUsersResult` |
| `get_type_info` | Resolve type information for an expression or symbol. | `TypeInfo` |
| `get_completions` | Return completion candidates for a cursor location. | `list[CompletionItem]` |
| `get_signature_help` | Return active signature and parameter help at a call site. | `SignatureInfo \| None` |
| `get_documentation` | Return Jedi help/doc entries for a symbol position. | `DocumentationResult` |
| `get_document_highlights` | Return in-file read/write highlights for a symbol. | `list[DocumentHighlight]` |
| `get_inlay_hints` | Return inlay hints (type/parameter hints) for a file range. | `list[InlayHint]` |
| `get_semantic_tokens` | Return semantic token classifications for a file. | `list[SemanticToken]` |
| `get_diagnostics` | Return Pyright diagnostics for a file. | `list[Diagnostic]` |
| `get_workspace_diagnostics` | Summarize diagnostics per file across the workspace. | `list[DiagnosticSummary]` |
| `deep_type_inference` | Run deep type inference on an expression or block. | `TypeInfo` |
| `get_type_hint_string` | Return a type hint string for a symbol position. | `str` |
| `get_syntax_errors` | Return parse-level syntax errors for a file. | `list[SyntaxErrorItem]` |
| `get_context` | Return surrounding code context for a position. | `ContextResult` |
| `get_all_names` | Return all names defined or imported in a file. | `list[NameInfo]` |
| `create_type_stubs` | Generate type stubs for a package. | `bool` |

## Navigation (10)

| Tool | Purpose | Returns |
|---|---|---|
| `goto_definition` | Navigate to symbol definitions. | `list[Location]` |
| `get_declaration` | Navigate to declaration sites (stub/interface). | `list[Location]` |
| `get_type_definition` | Navigate to type definitions for a symbol. | `list[Location]` |
| `find_implementations` | Navigate to concrete implementation locations. | `list[Location]` |
| `get_folding_ranges` | Return foldable code regions for chunked analysis. | `list[FoldingRange]` |
| `get_symbol_outline` | Return a hierarchical symbol outline for a file or workspace. | `list[SymbolOutlineItem]` |
| `call_hierarchy` | Return callers and callees for a symbol. | `CallHierarchyResult` |
| `type_hierarchy` | Return supertypes/subtypes for a class/type symbol. | `TypeHierarchyResult` |
| `selection_range` | Return nested selection ranges for one or more positions. | `list[SelectionRangeResult]` |
| `get_module_public_api` | Return the public API surface of a module. | `list[PublicAPIItem]` |

## Refactoring (32)

| Tool | Purpose | Returns |
|---|---|---|
| `prepare_rename` | Validate whether rename is allowed at a position. | `PrepareRenameResult \| None` |
| `rename_symbol` | Generate or apply a rope rename. | `RefactorResult` |
| `extract_method` | Extract a selected block into a method. | `RefactorResult` |
| `extract_variable` | Extract an expression into a variable. | `RefactorResult` |
| `inline_variable` | Inline a variable definition and usages. | `RefactorResult` |
| `inline_method` | Inline a method at all call sites. | `RefactorResult` |
| `inline_parameter` | Inline a parameter and remove it from the signature. | `RefactorResult` |
| `move_symbol` | Move a symbol between files. | `RefactorResult` |
| `move_module` | Move a module to a new location. | `RefactorResult` |
| `move_method` | Move a method to another class. | `RefactorResult` |
| `introduce_parameter` | Introduce a parameter and update call sites. | `RefactorResult` |
| `encapsulate_field` | Encapsulate a field with property-style accessors. | `RefactorResult` |
| `local_to_field` | Promote a local variable to an instance field. | `RefactorResult` |
| `method_object` | Extract complex method logic into a method-object class. | `RefactorResult` |
| `introduce_factory` | Introduce factory-based construction helpers for classes. | `RefactorResult` |
| `module_to_package` | Convert a Python module file into a package layout. | `RefactorResult` |
| `generate_code` | Generate code scaffolding for a symbol or pattern. | `RefactorResult` |
| `change_signature` | Add/remove/reorder parameters and update call sites. | `RefactorResult` |
| `argument_normalizer` | Normalize positional arguments to keyword form. | `RefactorResult` |
| `argument_default_inliner` | Inline default argument values at call sites. | `RefactorResult` |
| `restructure` | Apply Rope pattern-based structural replacements. | `RefactorResult` |
| `use_function` | Replace duplicate code with calls to an existing function. | `RefactorResult` |
| `apply_code_action` | Preview or apply a Pyright code action at a source position. | `RefactorResult` |
| `organize_imports` | Preview or apply import organization for a file. | `RefactorResult` |
| `format_code` | Preview or apply ruff-format on one or more files. | `RefactorResult` |
| `apply_lint_fixes` | Preview or apply ruff `--fix` on one or more files; supports `unsafe_fixes`. | `RefactorResult` |
| `apply_type_annotations` | Materialize Pyright-inferred type hints into real source annotations. | `RefactorResult` |
| `expand_star_imports` | Expand `import *` to explicit names. | `RefactorResult` |
| `relatives_to_absolutes` | Convert relative imports to absolute. | `RefactorResult` |
| `froms_to_imports` | Convert `from X import Y` to `import X.Y` form. | `RefactorResult` |
| `handle_long_imports` | Break long import lines into shorter form. | `RefactorResult` |
| `fix_module_names` | Fix incorrect module references across the workspace. | `RefactorResult` |

## Search (8)

| Tool | Purpose | Returns |
|---|---|---|
| `find_constructors` | Locate constructor call sites for a class. | `list[ConstructorSite]` |
| `search_symbols` | Search workspace symbols by name across semantic backends. | `list[SymbolInfo]` |
| `structural_search` | Search Python code using LibCST matcher expressions. | `list[StructuralMatch]` |
| `dead_code_detection` | Identify likely dead symbols and unused code. | `list[DeadCodeItem]` |
| `suggest_imports` | Suggest import statements for unresolved symbols. | `list[ImportSuggestion]` |
| `autoimport_search` | Search autoimport database for a symbol name. | `list[ImportSuggestion]` |
| `find_unused_imports` | Find unused imports in a file. | `list[UnusedImport]` |
| `project_search` | Project-wide semantic symbol search via Jedi. | `list[SymbolInfo]` |

## Metrics and Architecture (10)

| Tool | Purpose | Returns |
|---|---|---|
| `code_metrics` | Return complexity and quality metrics for a file. | `CodeMetrics` |
| `get_module_dependencies` | Return import dependency graph for a file. | `list[Dependency]` |
| `get_type_coverage` | Return type annotation coverage for a file. | `TypeCoverage` |
| `get_coupling_metrics` | Return coupling metrics between modules. | `CouplingMetrics` |
| `check_layer_violations` | Detect layer boundary violations in the codebase. | `list[LayerViolation]` |
| `interface_conformance` | Check class conformance to an interface or protocol. | `ConformanceResult` |
| `extract_protocol` | Extract a Protocol interface from class usage patterns. | `RefactorResult` |
| `find_duplicated_code` | Identify duplicated code blocks in a file or workspace. | `list[DuplicateBlock]` |
| `find_errors_static` | Rope-based static analysis for bad name/attribute accesses. | `list[StaticError]` |
| `get_test_coverage_map` | Map source symbols to their test references. | `list[CoverageMapItem]` |

## History and Change Management (6)

| Tool | Purpose | Returns |
|---|---|---|
| `undo_refactoring` | Undo the last N refactoring operations via Rope history. | `RefactorResult` |
| `redo_refactoring` | Redo the last N undone refactoring operations. | `RefactorResult` |
| `get_refactoring_history` | Return the current Rope refactoring history stack. | `list[HistoryEntry]` |
| `begin_change_stack` | Start a Rope ChangeStack for grouping refactorings. | `str` |
| `commit_change_stack` | Commit all changes in the current ChangeStack. | `RefactorResult` |
| `rollback_change_stack` | Roll back all changes in the current ChangeStack. | `str` |

## Composite and Utilities (8)

| Tool | Purpose | Returns |
|---|---|---|
| `diff_preview` | Build unified diffs for pending text edits. | `list[DiffPreview]` |
| `get_keyword_help` | Return help for a Python keyword or operator. | `KeywordHelp` |
| `get_sub_definitions` | Return names defined within a symbol via Jedi. | `list[NameInfo]` |
| `simulate_execution` | Simulate execution of a name to infer results via Jedi. | `list[NameInfo]` |
| `list_environments` | Discover available Python environments and virtualenvs. | `list[EnvironmentInfo]` |
| `restart_server` | Restart the Pyright language server. | `str` |
| `multi_project_rename` | Rename a symbol across multiple Rope projects simultaneously. | `RefactorResult` |
| `security_scan` | AST-based SAST security scan for a file. | `list[SecurityIssue]` |
