# 01 — Inventory (live `tools/list`, `resources/list`, `resources/templates/list`, `prompts/list`)

Source: `raw/inventory_refactoring.json`, `raw/inventory_analysis.json` (full initialize result + every tool schema verbatim).

| Item | refactoring profile | analysis profile | Union |
|---|---|---|---|
| Tools | 75 | 56 | 108 unique (23 shared) |
| Resources | 0 | 0 | 0 |
| Resource templates | 0 | 0 | 0 |
| Prompts | 0 | 0 | 0 |
| `tools/list` pagination | single page (`nextCursor` null) | single page | — |
| Startup (spawn → initialize, pre-warm) | 3.18 s | 2.79 s | — |
| Advertised capabilities | `tools`, `resources{subscribe:false}`, `prompts` (all `listChanged:false`) | same | — |
| Profile schema drift | none — the 23 shared tools have byte-identical schemas in both profiles | | |

Profile rule (`tool_registry.py:1736-1741`): analysis = every `readOnlyHint=true` record; refactoring = every non-read-only record + `_REFACTORING_SUPPORT_TOOLS` (`tool_registry.py:1606-1632`). Budget `MAX_TOOLS_PER_PROFILE = 80` (`:1601`).

## Tools

Profiles: R = refactoring, A = analysis. Hints: RO = `readOnlyHint`, destructive = `destructiveHint`, additive = neither.

| Tool name | Profiles | Hints | Description (first sentence) | Input schema fields (* = required) | Output shape |
|---|---|---|---|---|---|
| `apply_code_action` | R | additive | Apply a Pyright code action (quick fix, refactoring suggestion) at a location. | *`file_path`:string, *`line`:integer, *`character`:integer, `action_title`:string\|null, `apply`:boolean | RefactorResult |
| `apply_lint_fixes` | R | additive | Run `ruff check --fix` on one or more files (respects project pyproject.toml / ruff.toml). | *`file_path`:string, `apply`:boolean, `file_paths`:list[string]\|null, `unsafe_fixes`:boolean | RefactorResult |
| `apply_type_annotations` | R | additive | Materialize Pyright-inferred type hints into real source-level annotations. | *`file_path`:string, `apply`:boolean, `file_paths`:list[string]\|null | RefactorResult |
| `argument_default_inliner` | R | destructive | Inline a parameter's default value into all call sites that omit it, then remove the default from the signature. | *`file_path`:string, *`line`:integer, *`character`:integer, *`index`:integer, `apply`:boolean | RefactorResult |
| `argument_normalizer` | R | destructive | Normalize call-site arguments to match the function definition's parameter order. | *`file_path`:string, *`line`:integer, *`character`:integer, `apply`:boolean | RefactorResult |
| `autoimport_search` | R+A | RO | Search for importable names using rope's SQLite-backed AutoImport cache. | *`name`:string | {result: list[ImportSuggestion]} |
| `begin_change_stack` | R | additive | Start an atomic change stack for chaining multiple refactorings. | — | {result: string} |
| `call_hierarchy` | A | RO | Discover which functions call a given function (callers) and which functions it calls (callees). | *`file_path`:string, *`line`:integer, *`character`:integer, `direction`:string, `depth`:integer, `max_items`:integer\|null | CallHierarchyResult |
| `change_signature` | R | destructive | Modify a function's signature — add, remove, reorder, or rename parameters — and update all call sites. | *`file_path`:string, *`line`:integer, *`character`:integer, *`operations`:list[SignatureOperation], `apply`:boolean | RefactorResult |
| `check_layer_violations` | A | RO | Check import directions against declared layering rules. | *`layers`:list[list[string]], `file_paths`:list[string]\|null | LayerViolationResult |
| `check_type_stub_freshness` | A | RO | Compare a Python module's public callable signatures with its `.pyi` stub. | *`source_file`:string, `stub_file`:string\|null | TypeStubFreshnessResult |
| `code_metrics` | A | RO | Compute cyclomatic complexity, cognitive complexity, nesting depth, lines of code, and parameter count for all functions. | *`file_path`:string, `file_paths`:list[string]\|null | CodeMetricsResult |
| `commit_change_stack` | R | destructive | Commit and apply the current change stack atomically. | — | RefactorResult |
| `convert_function_to_method` | R | destructive | Move a top-level function into a plain class and rewrite every direct caller in the definition module from `function(instance, ...)` to `instance.function(...)`. | *`file_path`:string, *`function_name`:string, *`class_name`:string, `apply`:boolean | RefactorResult |
| `convert_method_to_function` | R | destructive | Move a direct instance method from a plain class to module scope and rewrite every direct caller in that module from `instance.method(...)` to `method(instance, ...)`. | *`file_path`:string, *`class_name`:string, *`method_name`:string, `apply`:boolean | RefactorResult |
| `convert_to_dataclass` | R | destructive | Convert a behavior-free class constructor into standard-library `@dataclass` fields. | *`file_path`:string, *`class_name`:string, `apply`:boolean | RefactorResult |
| `convert_to_pydantic` | R | destructive | Convert one plain class with a fully typed keyword-only constructor into a Pydantic v2 model. | *`file_path`:string, *`class_name`:string, `apply`:boolean | RefactorResult |
| `convert_to_typeddict` | R | destructive | Convert a top-level function's consistent dict-literal returns into a generated `TypedDict`. | *`file_path`:string, *`function_name`:string, *`typed_dict_name`:string, `apply`:boolean | RefactorResult |
| `create_type_stubs` | R | additive | Generate .pyi type stub files for a third-party package lacking type information. | *`package_name`:string, `output_dir`:string\|null | {result: boolean} |
| `dead_code_detection` | R+A | RO | Find unreferenced functions, classes, and variables that may be dead code. | `file_path`:string\|null, `exclude_patterns`:list[string]\|null, `root_path`:string\|null, `exclude_test_files`:boolean, `file_paths`:list[string]\|null, `offset`:integer, `limit`:integer\|null | PaginatedDeadCode |
| `deep_type_inference` | A | RO | Follow imports and statements to resolve final types at a position. | *`file_path`:string, *`line`:integer, *`character`:integer | {result: list[InferredType]} |
| `diff_preview` | R+A | RO | Generate unified diff previews for a list of TextEdit objects. | *`edits`:list[TextEdit] | {result: list[DiffPreview]} |
| `docstring_sync` | R | destructive | Synchronize one function signature with its existing Google, NumPy, or Sphinx docstring parameter fields. | *`file_path`:string, *`line`:integer, *`character`:integer, `style`:string, `apply`:boolean | RefactorResult |
| `encapsulate_field` | R | destructive | Wrap a class field with property getter/setter accessors, updating all direct field accesses. | *`file_path`:string, *`line`:integer, *`character`:integer, `apply`:boolean | RefactorResult |
| `expand_star_imports` | R | additive | Replace ``from x import *`` with explicit named imports. | *`file_path`:string, `apply`:boolean | RefactorResult |
| `extract_class` | R | destructive | Move direct constructor fields and plain instance methods into a new collaborator while preserving the source class API through field properties and method delegates. | *`file_path`:string, *`class_name`:string, *`new_class_name`:string, *`members`:list[string], *`collaborator_attribute`:string, `apply`:boolean | RefactorResult |
| `extract_method` | R | destructive | Extract a code selection into a new method, automatically detecting parameters and return values. | *`file_path`:string, *`start_line`:integer, *`start_character`:integer, *`end_line`:integer, *`end_character`:integer, *`method_name`:string, `similar`:boolean, `apply`:boolean | RefactorResult |
| `extract_protocol` | A | RO | Generate a Protocol class from common methods of given classes. | *`file_path`:string, *`class_names`:list[string], `protocol_name`:string | ProtocolSource |
| `extract_superclass` | R | destructive | Pull a named subset of methods and class-level attributes up into a new base class, inserted immediately before the source class. | *`file_path`:string, *`class_name`:string, *`base_class_name`:string, *`members`:list[string], `apply`:boolean | RefactorResult |
| `extract_variable` | R | destructive | Extract an expression into a named variable, replacing the original expression with the variable name. | *`file_path`:string, *`start_line`:integer, *`start_character`:integer, *`end_line`:integer, *`end_character`:integer, *`variable_name`:string, `apply`:boolean | RefactorResult |
| `find_constructors` | A | RO | Find all places where a class is instantiated (constructor calls). | *`class_name`:string, `file_path`:string\|null, `limit`:integer\|null | ConstructorSearchResult |
| `find_duplicated_code` | A | RO | Detect duplicated function bodies by normalizing AST and comparing hashes. | *`file_path`:string, `file_paths`:list[string]\|null, `min_lines`:integer | DuplicateCodeResult |
| `find_errors_static` | R+A | RO | Run rope's static analysis for bad name/attribute accesses. | *`file_path`:string | {result: list[StaticError]} |
| `find_implementations` | A | RO | Find concrete implementations of an abstract method or protocol. | *`file_path`:string, *`line`:integer, *`character`:integer | {result: list[Location]} |
| `find_references` | R+A | RO | Find all references to a symbol across the workspace. | *`file_path`:string, *`line`:integer, *`character`:integer, `include_declaration`:boolean, `include_context`:boolean, `limit`:integer\|null | ReferenceResult |
| `find_type_users` | A | RO | Inverse of `find_references` scoped to a type — classify every reference site as `annotation` (type-hint position incl. | *`file_path`:string, *`line`:integer, *`character`:integer, `kinds`:list[string]\|null, `include_declaration`:boolean, `limit`:integer\|null | TypeUsersResult |
| `find_unused_imports` | R+A | RO | Find unused imports using Pyright diagnostics merged with an AST fallback. | `file_path`:string\|null, `file_paths`:list[string]\|null | UnusedImportScanResult |
| `fix_circular_imports` | R | destructive | Break runtime import cycles by moving only imports proven annotation-only behind `if TYPE_CHECKING:` and stringifying the affected annotations when needed. | `file_path`:string\|null, `file_paths`:list[string]\|null, `apply`:boolean | RefactorResult |
| `fix_module_names` | R | destructive | Batch-rename modules to conform to PEP 8 lowercase naming conventions, updating all imports. | `apply`:boolean | RefactorResult |
| `format_code` | R | additive | Run ruff-format on one or more files (respects project pyproject.toml / ruff.toml). | *`file_path`:string, `apply`:boolean, `file_paths`:list[string]\|null | RefactorResult |
| `froms_to_imports` | R | additive | Convert ``from module import name`` to ``import module`` style. | *`file_path`:string, `apply`:boolean | RefactorResult |
| `generate_code` | R | destructive | Generate a missing class, function, variable, module, or package from a usage site. | *`file_path`:string, *`line`:integer, *`character`:integer, *`kind`:string, `apply`:boolean | RefactorResult |
| `get_all_names` | A | RO | List all defined names in a file with optional nested scopes. | *`file_path`:string, `all_scopes`:boolean, `references`:boolean | {result: list[NameEntry]} |
| `get_completions` | A | RO | Get code completion candidates at a cursor position. | *`file_path`:string, *`line`:integer, *`character`:integer, `limit`:integer\|null, `fuzzy`:boolean | {result: list[CompletionItem]} |
| `get_context` | A | RO | Return the enclosing function, class, or module scope at a position. | *`file_path`:string, *`line`:integer, *`character`:integer | {result: ScopeContext\|null} |
| `get_coupling_metrics` | A | RO | Compute afferent/efferent coupling and instability per module. | `file_paths`:list[string]\|null | CouplingMetricsResult |
| `get_declaration` | A | RO | Navigate to the declaration site of a symbol (where it is first declared, not necessarily defined). | *`file_path`:string, *`line`:integer, *`character`:integer | {result: list[Location]} |
| `get_diagnostics` | R+A | RO | Get type-checking diagnostics (errors, warnings, hints) for one file, a batch of files, or the full project. | `file_path`:string\|null, `severity_filter`:string\|null, `limit`:integer\|null, `suppress_codes`:list[string]\|null, `file_paths`:list[string]\|null | {result: list[Diagnostic]} |
| `get_document_highlights` | A | RO | Highlight all read and write accesses of a symbol within a single file. | *`file_path`:string, *`line`:integer, *`character`:integer | {result: list[DocumentHighlight]} |
| `get_documentation` | A | RO | Get detailed documentation and docstrings for a symbol. | *`file_path`:string, *`line`:integer, *`character`:integer, `source`:string\|null | DocumentationResult |
| `get_folding_ranges` | A | RO | Get foldable code regions (functions, classes, if blocks, import groups) in a file. | *`file_path`:string | {result: list[FoldingRange]} |
| `get_inlay_hints` | A | RO | Get inlay hints (inline type annotations, parameter names) for a file range. | *`file_path`:string, `start_line`:integer, `start_character`:integer, `end_line`:integer\|null, `end_character`:integer | {result: list[InlayHint]} |
| `get_keyword_help` | A | RO | Documentation for Python keywords and operators. | *`file_path`:string, *`line`:integer, *`character`:integer | DocumentationResult |
| `get_module_dependencies` | R+A | RO | Build an import dependency graph with circular dependency detection. | `file_path`:string\|null, `file_paths`:list[string]\|null | DependencyGraph |
| `get_module_public_api` | A | RO | Return only exported symbols from a module. | *`file_path`:string | {result: list[PublicAPIItem]} |
| `get_refactoring_history` | R+A | RO | Get the refactoring change history. | — | {result: list[HistoryEntry]} |
| `get_semantic_tokens` | A | RO | Get semantic token classifications for a file. | *`file_path`:string, `limit`:integer\|null | {result: list[SemanticToken]} |
| `get_signature_help` | A | RO | Get function signature help at a call site. | *`file_path`:string, *`line`:integer, *`character`:integer | {result: SignatureInfo\|null} |
| `get_sub_definitions` | A | RO | List sub-definitions of a name (e.g., methods of a class from a reference). | *`file_path`:string, *`line`:integer, *`character`:integer | {result: list[NameEntry]} |
| `get_symbol_outline` | R+A | RO | Get a hierarchical outline of classes, functions, and variables in a file or across the workspace. | `file_path`:string\|null, `kind_filter`:list[string]\|null, `name_pattern`:string\|null, `limit`:integer\|null, `root_path`:string\|null, `file_paths`:list[string]\|null, `offset`:integer | {result: list[SymbolOutlineItem]} |
| `get_syntax_errors` | R+A | RO | Detect syntax errors via Jedi's parser. | *`file_path`:string | {result: list[SyntaxErrorItem]} |
| `get_test_coverage_map` | A | RO | Map source symbols to test references. | `file_path`:string\|null, `file_paths`:list[string]\|null | TestCoverageMap |
| `get_type_coverage` | A | RO | Report type annotation completeness for function parameters and return types, including partial file scans in scan_failures. | *`file_path`:string, `file_paths`:list[string]\|null | TypeCoverageReport |
| `get_type_definition` | A | RO | Navigate to the type definition of a symbol (e.g., from a variable to its class definition). | *`file_path`:string, *`line`:integer, *`character`:integer | {result: list[Location]} |
| `get_type_hint_string` | A | RO | Return ready-to-use type annotation strings like ``Iterable[int]`` for a symbol. | *`file_path`:string, *`line`:integer, *`character`:integer | {result: list[TypeHintResult]} |
| `get_type_info` | R+A | RO | Infer the type of a symbol or expression at a source position. | *`file_path`:string, *`line`:integer, *`character`:integer | TypeInfo |
| `get_workspace_diagnostics` | R+A | RO | Get aggregated diagnostic counts (errors, warnings, hints) per file across the workspace. | `root_path`:string\|null, `suppress_codes`:list[string]\|null, `file_paths`:list[string]\|null, `offset`:integer, `limit`:integer\|null | Paginated[DiagnosticSummary] |
| `goto_definition` | R+A | RO | Jump to where a symbol is defined. | *`file_path`:string, *`line`:integer, *`character`:integer | {result: list[Location]} |
| `handle_long_imports` | R | additive | Break long import lines per project preferences (maxdots, maxlength). | *`file_path`:string, `apply`:boolean | RefactorResult |
| `inline_method` | R | destructive | Inline a function/method body into all call sites and remove the original definition. | *`file_path`:string, *`line`:integer, *`character`:integer, `apply`:boolean | RefactorResult |
| `inline_parameter` | R | destructive | Remove a parameter by inlining its default value into the function body. | *`file_path`:string, *`line`:integer, *`character`:integer, `apply`:boolean | RefactorResult |
| `inline_variable` | R | destructive | Inline a variable — replace all usages with its assigned value and remove the assignment. | *`file_path`:string, *`line`:integer, *`character`:integer, `apply`:boolean | RefactorResult |
| `interface_conformance` | A | RO | Compare class interfaces to detect implicit protocol conformance. | *`file_path`:string, *`class_names`:list[string] | InterfaceComparison |
| `introduce_factory` | R | destructive | Create a factory function that wraps a class constructor, updating all direct instantiations to use the factory. | *`file_path`:string, *`line`:integer, *`character`:integer, `factory_name`:string\|null, `global_factory`:boolean, `apply`:boolean | RefactorResult |
| `introduce_parameter` | R | destructive | Convert a local expression into a function parameter, adding it to the signature and updating all call sites with a default value. | *`file_path`:string, *`line`:integer, *`character`:integer, *`parameter_name`:string, `default_value`:string, `apply`:boolean | RefactorResult |
| `list_environments` | R+A | RO | Discover and list Python environments and virtualenvs. | — | {result: list[EnvironmentInfo]} |
| `local_to_field` | R | destructive | Promote a local variable inside a method to an instance field (self.name), updating all usages within the class. | *`file_path`:string, *`line`:integer, *`character`:integer, `apply`:boolean | RefactorResult |
| `method_object` | R | destructive | Convert a method with complex logic into a callable object (functor class) with __call__. | *`file_path`:string, *`line`:integer, *`character`:integer, `classname`:string\|null, `apply`:boolean | RefactorResult |
| `module_to_package` | R | destructive | Convert a single-file module into a package (directory with __init__.py), preserving all imports. | *`file_path`:string, `apply`:boolean | RefactorResult |
| `move_method` | R | destructive | Move a method from one class to another, creating a delegate in the original class. | *`file_path`:string, *`line`:integer, *`character`:integer, *`destination_attr`:string, `apply`:boolean | RefactorResult |
| `move_module` | R | destructive | Move or rename an entire module or package, updating all imports across the project. | *`source_path`:string, *`destination_package`:string, `apply`:boolean | RefactorResult |
| `move_symbol` | R | destructive | Move a top-level symbol (function, class, variable) from one file to another, updating all imports across the project. | *`source_file`:string, *`symbol_name`:string, *`destination_file`:string, `apply`:boolean | RefactorResult |
| `multi_project_rename` | R | destructive | Rename a symbol across multiple Rope projects simultaneously. | *`additional_roots`:list[string], *`file_path`:string, *`line`:integer, *`character`:integer, *`new_name`:string, `apply`:boolean | RefactorResult |
| `organize_imports` | R | additive | Sort and group imports according to PEP 8 conventions. | *`file_path`:string, `apply`:boolean, `file_paths`:list[string]\|null | RefactorResult |
| `prepare_rename` | R+A | RO | Check if a symbol at a position can be renamed and return the editable range. | *`file_path`:string, *`line`:integer, *`character`:integer | {result: PrepareRenameResult\|null} |
| `project_search` | A | RO | Project-wide semantic search using Jedi analysis engine. | *`query`:string, `complete`:boolean | {result: list[SymbolInfo]} |
| `redo_refactoring` | R | destructive | Redo previously undone refactoring operations. | `count`:integer | RefactorResult |
| `refactor_transaction` | R | destructive | Apply an ordered list of refactorings atomically under one change stack — commit all on success, roll back all on any failure. | *`steps`:list[object] | TransactionResult |
| `relatives_to_absolutes` | R | additive | Convert all relative imports to absolute imports in a file. | *`file_path`:string, `apply`:boolean | RefactorResult |
| `rename_symbol` | R | destructive | Rename a symbol across the entire project — updates all references, imports, and usages. | *`file_path`:string, *`line`:integer, *`character`:integer, *`new_name`:string, `apply`:boolean, `include_diff`:boolean | RefactorResult |
| `restart_server` | R | destructive | Discard cached type info and restart Pyright analysis. | — | {result: string} |
| `restructure` | R | destructive | Apply pattern-based code transformations using rope's structural replace engine. | *`pattern`:string, *`goal`:string, `checks`:object\|null, `imports`:list[string]\|null, `file_path`:string\|null, `apply`:boolean | RefactorResult |
| `rollback_change_stack` | R | destructive | Discard the current change stack without applying. | — | {result: string} |
| `search_symbols` | R+A | RO | Search for symbols (functions, classes, variables) by name across the workspace. | *`query`:string, `limit`:integer\|null | SymbolSearchResult |
| `security_autofix` | R | destructive | Rewrite unsafe yaml.load() calls (SEC022) to yaml.safe_load(). | `file_path`:string\|null, `file_paths`:list[string]\|null, `apply`:boolean | RefactorResult |
| `security_scan` | R+A | RO | AST-based security scan for common Python vulnerabilities (eval, exec, shell injection, pickle, etc.). | `file_path`:string\|null, `file_paths`:list[string]\|null | SecurityScanResult |
| `selection_range` | R+A | RO | Get nested selection ranges (inner-most to outer-most scope) at source positions. | *`file_path`:string, *`positions`:list[Position] | {result: list[SelectionRangeResult]} |
| `server_status` | R+A | RO | Report read-only server health: version, known workspace roots, and per-workspace backend liveness (Pyright subprocess up, Jedi/rope ready). | — | ServerStatus |
| `simulate_execution` | A | RO | Simulate calling a callable and return result types. | *`file_path`:string, *`line`:integer, *`character`:integer | {result: list[TypeInfo]} |
| `split_module` | R | destructive | Partition selected top-level symbols from one module into two or more existing target modules. | *`source_file`:string, *`target_modules`:object, `apply`:boolean | RefactorResult |
| `structural_replace` | R | destructive | Find structural matches with a LibCST matcher pattern and rewrite them. | *`pattern`:string, *`replacement`:string, `file_path`:string\|null, `file_paths`:list[string]\|null, `apply`:boolean | RefactorResult |
| `structural_search` | R+A | RO | Search for code patterns using LibCST matcher expressions. | *`pattern`:string, `file_path`:string\|null, `language`:string, `limit`:integer\|null | StructuralSearchResult |
| `suggest_imports` | R+A | RO | Suggest import statements for an unresolved symbol name. | *`symbol`:string, *`file_path`:string | {result: list[ImportSuggestion]} |
| `test_impact_select` | R+A | RO | Given changed symbol anchors, return the pytest tests that transitively exercise them. | *`symbols`:list[SymbolAnchor], `depth`:integer, `max_items`:integer | TestImpactResult |
| `type_hierarchy` | A | RO | Discover class inheritance — supertypes (parents) and subtypes (children) of a class. | *`file_path`:string, *`line`:integer, *`character`:integer, `direction`:string, `depth`:integer, `max_items`:integer\|null, `class_name`:string\|null | TypeHierarchyResult |
| `undo_refactoring` | R | destructive | Undo the last refactoring operations. | `count`:integer | RefactorResult |
| `unused_symbol_sweep` | A | RO | Audit the public export surface for symbols with zero cross-file references. | `file_path`:string\|null, `exclude_patterns`:list[string]\|null, `root_path`:string\|null, `exclude_test_files`:boolean, `file_paths`:list[string]\|null, `offset`:integer, `limit`:integer\|null | PaginatedDeadCode |
| `use_function` | R | destructive | Find code blocks duplicating a function's body and replace them with calls to that function. | *`file_path`:string, *`line`:integer, *`character`:integer, `apply`:boolean | RefactorResult |

## Resources

| Resource URI pattern | MIME type | Description |
|---|---|---|
| — (none registered) | — | — |

## Prompts

| Prompt name | Description | Args |
|---|---|---|
| — (none registered) | — | — |
