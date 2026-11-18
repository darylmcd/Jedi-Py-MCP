# Tool Reference

Complete 108-tool catalog organized by category. A running server advertises
the bounded `refactoring` or `analysis` profile; see `setup.md` for selection.

Workspace selection: a tool that can be called without a file path (for
example `search_symbols`, `fix_module_names`, `undo_refactoring`)
accepts an absolute `root_path` naming its workspace; `root_path` only ever
selects a workspace. The four tools that scan a directory
(`get_workspace_diagnostics`, `get_symbol_outline`, `dead_code_detection`,
`unused_symbol_sweep`) take that directory as `directory` instead: it scopes
the scan and also selects the workspace containing it, and `root_path` is
rejected there. Without either it uses only the sole workspace a path-bearing call
already selected, and otherwise fails with `[AMBIGUOUS_WORKSPACE]` listing the
live roots. `server_status` needs no workspace. See
[ADR 0007](adr/0007-explicit-workspace-selection.md) and
[ADR 0012](adr/0012-scan-directory-parameter.md).

Paths: every path argument must be a local path. UNC and device-namespace
paths (`\\server\share`, `\\?\UNC\...`, `\\.\...`) are refused with
`[INVALID_INPUT]` before any filesystem access; map the share to a drive
letter. See [ADR 0011](adr/0011-reject-unc-and-device-paths.md).

## Analysis (19)

| Tool | Purpose | Returns |
|---|---|---|
| `find_references` | Find all references to a symbol and expose optional-backend failures separately from usable locations. | `ReferenceResult` |
| `find_type_users` | Inverse of `find_references` scoped to a type — classify sites as annotation / instantiation / subclass / other. | `TypeUsersResult` |
| `get_type_info` | Resolve type information for an expression or symbol. | `TypeInfo` |
| `get_completions` | Return completion candidates for a cursor location. | `list[CompletionItem]` |
| `get_signature_help` | Return active signature and parameter help at a call site. | `SignatureInfo \| None` |
| `get_documentation` | Return Jedi help/doc entries for a symbol position. | `DocumentationResult` |
| `get_document_highlights` | Return in-file read/write highlights for a symbol. | `list[DocumentHighlight]` |
| `get_inlay_hints` | Return inlay hints (type/parameter hints) for a file range. | `list[InlayHint]` |
| `get_semantic_tokens` | Return semantic token classifications for a file. | `list[SemanticToken]` |
| `get_diagnostics` | Return Pyright diagnostics for a file, a `file_paths` batch, or (neither given) every Python file of the workspace; the workspace form raises if any file cannot be read. | `list[Diagnostic]` |
| `get_workspace_diagnostics` | Summarize diagnostics per file across the workspace. | `PaginatedDiagnosticSummary` |
| `deep_type_inference` | Run deep type inference on an expression or block. | `list[InferredType]` |
| `get_type_hint_string` | Return type hint candidates for a symbol position. | `list[TypeHintResult]` |
| `get_syntax_errors` | Return parse-level syntax errors for a file. | `list[SyntaxErrorItem]` |
| `get_context` | Return surrounding scope context for a position when available. | `ScopeContext \| None` |
| `get_all_names` | Return all names defined or imported in a file. | `list[NameEntry]` |
| `create_type_stubs` | Generate `.pyi` stubs for a package via the Pyright CLI; writes immediately (no preview) to `<workspace>/typings/<package>` or a workspace-bounded `output_dir`. | `TypeStubCreationResult` |
| `check_type_stub_freshness` | Compare a module's callable API shape with its `.pyi` stub. | `TypeStubFreshnessResult` |
| `test_impact_select` | Select pytest tests that transitively exercise changed symbol anchors via call-hierarchy. | `TestImpactResult` |

## Navigation (10)

| Tool | Purpose | Returns |
|---|---|---|
| `goto_definition` | Navigate to symbol definitions. | `list[Location]` |
| `get_declaration` | Navigate to declaration sites (stub/interface). | `list[Location]` |
| `get_type_definition` | Navigate to type definitions for a symbol. | `list[Location]` |
| `find_implementations` | Navigate to concrete implementation locations. | `list[Location]` |
| `get_folding_ranges` | Return foldable code regions for chunked analysis. | `list[FoldingRange]` |
| `get_symbol_outline` | Return a hierarchical symbol outline for a file or workspace. `limit` counts root items and `max_nodes` counts roots plus descendants; workspace scans default to 500 roots / 250 nodes. Check `truncated`. | `SymbolOutlineResult` |
| `call_hierarchy` | Return callers and callees for a symbol. | `CallHierarchyResult` |
| `type_hierarchy` | Return supertypes/subtypes for a class/type symbol. | `TypeHierarchyResult` |
| `selection_range` | Return nested selection ranges for one or more positions. | `list[SelectionRangeResult]` |
| `get_module_public_api` | Return the public API surface of a module. | `list[PublicAPIItem]` |

## Refactoring (42)

| Tool | Purpose | Returns |
|---|---|---|
| `prepare_rename` | Validate whether rename is allowed at a position. | `PrepareRenameResult \| None` |
| `rename_symbol` | Generate or apply a rope rename. | `RefactorResult` |
| `extract_method` | Extract a selected block into a method. | `RefactorResult` |
| `extract_class` | Move cohesive constructor fields and plain instance methods into a delegated collaborator (LibCST). | `RefactorResult` |
| `extract_superclass` | Pull selected methods/attributes up into a new base class (LibCST). | `RefactorResult` |
| `convert_to_dataclass` | Convert a behavior-free constructor into preview-first standard-library dataclass fields, using Pyright for missing annotations. | `RefactorResult` |
| `convert_to_pydantic` | Convert one bounded keyword-only validated class into a preview-first Pydantic v2 model; unsafe constructor and class shapes fail closed. | `RefactorResult` |
| `convert_to_typeddict` | Convert consistent dict-literal function returns into a generated TypedDict, using Pyright for concrete field types. | `RefactorResult` |
| `convert_function_to_method` | Move a free function into a plain class and rewrite direct same-module callers; unsupported reference shapes fail closed. | `RefactorResult` |
| `convert_method_to_function` | Move a direct instance method to module scope and rewrite direct same-module callers; unsupported reference shapes fail closed. | `RefactorResult` |
| `docstring_sync` | Synchronize function parameters with Google, NumPy, or Sphinx docstring fields, preserving descriptions in preview-first edits. | `RefactorResult` |
| `fix_circular_imports` | Hoist annotation-only runtime-cycle imports behind `TYPE_CHECKING`; mixed/runtime uses remain unchanged. | `RefactorResult` |
| `extract_variable` | Extract an expression into a variable. | `RefactorResult` |
| `inline_variable` | Inline a variable definition and usages. | `RefactorResult` |
| `inline_method` | Inline a method at all call sites. | `RefactorResult` |
| `inline_parameter` | Inline a parameter and remove it from the signature. | `RefactorResult` |
| `move_symbol` | Move a symbol between files. | `RefactorResult` |
| `split_module` | Partition selected top-level symbols into two or more existing modules with coherent import rewrites. | `RefactorResult` |
| `move_module` | Move a module to a new location. | `RefactorResult` |
| `move_method` | Move a method to another class. | `RefactorResult` |
| `introduce_parameter` | Introduce a parameter and update call sites. | `RefactorResult` |
| `encapsulate_field` | Encapsulate a field with property-style accessors. | `RefactorResult` |
| `local_to_field` | Promote a local variable to an instance field. | `RefactorResult` |
| `method_object` | Extract complex method logic into a method-object class. | `RefactorResult` |
| `introduce_factory` | Introduce factory-based construction helpers for classes. | `RefactorResult` |
| `module_to_package` | Convert a Python module file into a package layout. | `RefactorResult` |
| `generate_code` | Generate code scaffolding for a symbol or pattern. | `RefactorResult` |
| `change_signature` | Add/remove/reorder/rename parameters and update call sites. Every operation refuses (`ToolInputError`, nothing written) a target with `*args` (rope cannot rewrite its header), a position that is not a `def` function (lambda, class without `__init__`, variable), a call site that passes `**kwargs` to the target, and a workspace with non-NFKC identifiers that rope cannot parse; the last two name `path:line`. `add` and `reorder` refuse a final signature with a required parameter after a defaulted one, and `reorder` refuses a `new_order` that is not a permutation of the positional parameter indexes. Every operation also refuses a target when rope would rewrite another same-named definition (redefinition, conditional `def`, `@overload`, property setter; a same-named method of another class is fine; an annotated same-named definition is refused even when its parameters are unchanged, because rope drops annotations). Every operation also refuses a target with keyword-only (`*`) or positional-only (`/`) parameters, which rope cannot re-emit. `rename` keeps the parameter position, default and call arguments and renames its body bindings; it refuses (`ToolInputError`, nothing written) async functions (all operations), dynamic frame access (`locals`, `vars`, `eval`, `exec`, `dir`, `_getframe`, `currentframe`, `f_locals`), and any rename it cannot prove equivalent by comparing compiled code. rope drops parameter annotations on every operation (the tool restores them) and keeps the return annotation. Refused names also include `getargvalues` and `stack`. Refusals are not exhaustive: aliases of `eval`, `functools.partial(f, b=2)` and `**{"b": ...}` callers, `__code__.co_varnames`, `inspect.signature` and subclass overrides are not detected (see ADR 0004). The checks can over-refuse benignly (for example a parameter named like a module-level import); refusal is fail-closed. | `RefactorResult` |
| `argument_normalizer` | Normalize positional arguments to keyword form. | `RefactorResult` |
| `argument_default_inliner` | Inline default argument values at call sites. | `RefactorResult` |
| `restructure` | Apply Rope pattern-based structural replacements. | `RefactorResult` |
| `use_function` | Replace duplicate code with calls to an existing function. | `RefactorResult` |
| `apply_code_action` | Preview or apply a Pyright code action at a source position; omit `action_title` to list the offered titles. | `CodeActionResult` |
| `organize_imports` | Preview or apply import organization for a file. | `RefactorResult` |
| `format_code` | Preview or apply ruff-format on one or more files. | `RefactorResult` |
| `apply_lint_fixes` | Preview or apply ruff `--fix` on one or more files; supports `unsafe_fixes`. | `RefactorResult` |
| `apply_type_annotations` | Materialize Pyright-inferred type hints into real source annotations. | `RefactorResult` |
| `expand_star_imports` | Expand `import *` to explicit names. | `RefactorResult` |
| `relatives_to_absolutes` | Convert relative imports to absolute. | `RefactorResult` |
| `froms_to_imports` | Convert `from X import Y` to `import X.Y` form. | `RefactorResult` |
| `handle_long_imports` | Break long import lines into shorter form. | `RefactorResult` |
| `fix_module_names` | Fix incorrect module references across the workspace. | `RefactorResult` |

## Search (10)

| Tool | Purpose | Returns |
|---|---|---|
| `find_constructors` | Locate constructor call sites and report partial file/reference failures. | `ConstructorSearchResult` |
| `search_symbols` | Search workspace symbols by name across semantic backends and report partial backend failures. `limit` defaults to 200 (`null` for all); check `truncated`. | `SymbolSearchResult` |
| `structural_search` | Search Python code using LibCST matcher expressions. | `StructuralSearchResult` |
| `structural_replace` | Rewrite LibCST matcher matches using `$name` capture templates. | `RefactorResult` |
| `dead_code_detection` | Identify likely dead symbols and unused code. `limit` defaults to 200 (`null` for all); check `truncated`. | `PaginatedDeadCode` |
| `unused_symbol_sweep` | Project-wide audit of public exports with zero cross-file references. | `PaginatedDeadCode` |
| `suggest_imports` | Suggest import statements for unresolved symbols. | `list[ImportSuggestion]` |
| `autoimport_search` | Search autoimport database for a symbol name. | `list[ImportSuggestion]` |
| `find_unused_imports` | Find unused imports and report partial file/backend failures. | `UnusedImportScanResult` |
| `project_search` | Project-wide semantic symbol search via Jedi. | `list[SymbolInfo]` |

## Metrics and Architecture (10)

| Tool | Purpose | Returns |
|---|---|---|
| `code_metrics` | Return complexity metrics plus partial-scan failures. `functions` is sorted by cyclomatic complexity (highest first) and capped by `limit` (default 200, `null` for all); aggregates cover every function. Check `truncated`. | `CodeMetricsResult` |
| `get_module_dependencies` | Return an import dependency graph plus partial-scan failures. `limit` (default 500, `null` for all) caps only `dependencies`; `modules` and cycles stay complete. Check `truncated` / `total_dependencies`. | `DependencyGraph` |
| `get_type_coverage` | Return type annotation coverage plus partial-scan failures. | `TypeCoverageReport` |
| `get_coupling_metrics` | Return coupling metrics plus dependency-scan failures. | `CouplingMetricsResult` |
| `check_layer_violations` | Detect layer violations and report partial file failures. | `LayerViolationResult` |
| `interface_conformance` | Check class conformance to an interface or protocol. | `InterfaceComparison` |
| `extract_protocol` | Extract a Protocol interface from class usage patterns. | `ProtocolSource` |
| `find_duplicated_code` | Identify duplicated code blocks and report partial file failures. | `DuplicateCodeResult` |
| `find_errors_static` | Rope-based static analysis for bad name/attribute accesses. | `list[StaticError]` |
| `get_test_coverage_map` | Map source symbols to test references and report partial lookup failures. | `TestCoverageMap` |

## History and Change Management (6)

| Tool | Purpose | Returns |
|---|---|---|
| `undo_refactoring` | Undo the last N refactoring operations via Rope history. | `RefactorResult` |
| `redo_refactoring` | Redo the last N undone refactoring operations. | `RefactorResult` |
| `get_refactoring_history` | Return the current Rope refactoring history stack. | `list[HistoryEntry]` |
| `begin_change_stack` | Start a Rope ChangeStack for grouping refactorings. | `str` |
| `commit_change_stack` | Commit all changes in the current ChangeStack. | `RefactorResult` |
| `rollback_change_stack` | Roll back all changes in the current ChangeStack. | `str` |

## Composite and Utilities (11)

| Tool | Purpose | Returns |
|---|---|---|
| `diff_preview` | Build unified diffs for pending text edits; every edit path must be absolute and inside one workspace. | `list[DiffPreview]` |
| `refactor_transaction` | Apply an ordered `(tool, args)` list atomically under one change stack; commit on success, roll back all on any failure or overlap. | `TransactionResult` |
| `get_keyword_help` | Return help for a Python keyword or operator. | `DocumentationResult` |
| `get_sub_definitions` | Return names defined within a symbol via Jedi. | `list[NameEntry]` |
| `simulate_execution` | Simulate execution of a name to infer results via Jedi. | `list[TypeInfo]` |
| `list_environments` | Discover available Python environments and virtualenvs. | `list[EnvironmentInfo]` |
| `restart_server` | Restart the Pyright language server. | `str` |
| `multi_project_rename` | Rename a symbol across multiple Rope projects simultaneously. | `RefactorResult` |
| `security_scan` | AST-based SAST scan with explicit per-file failure metadata. | `SecurityScanResult` |
| `security_autofix` | Rewrite unsafe `yaml.load` (SEC022) to `yaml.safe_load` via LibCST; skips explicit `Loader=`. | `RefactorResult` |
| `server_status` | Read-only server health: version, workspace roots, per-backend liveness, degraded flag. | `ServerStatus` |
