# Python Refactor Domain Reference
<!-- purpose: Domain reference — 87 tools, workflows, key models for python-refactor-mcp. -->

Purpose: compact entry point for the Python refactor MCP domain.

## Core Files

- `src/python_refactor_mcp/server.py` — MCP app lifecycle, tool registration (87 tools)
- `src/python_refactor_mcp/config.py` — runtime config discovery
- `src/python_refactor_mcp/models.py` — shared Pydantic response models
- `src/python_refactor_mcp/backends/pyright_lsp.py` — Pyright LSP backend
- `src/python_refactor_mcp/backends/jedi_backend.py` — Jedi fallback backend
- `src/python_refactor_mcp/backends/rope_backend.py` — rope refactoring backend
- `src/python_refactor_mcp/tools/` — tool orchestration modules
- `src/python_refactor_mcp/util/` — LSP client, diff helpers, shared utilities

## Tool Surface (87 tools)

The canonical tool list is `server.py`. Tools are organized into these categories:

### Analysis (16 tools)
`find_references`, `get_type_info`, `get_completions`, `get_documentation`, `get_signature_help`, `get_document_highlights`, `get_inlay_hints`, `get_semantic_tokens`, `get_diagnostics`, `get_workspace_diagnostics`, `deep_type_inference`, `get_type_hint_string`, `get_syntax_errors`, `get_context`, `get_all_names`, `create_type_stubs`

### Navigation (10 tools)
`goto_definition`, `get_declaration`, `get_type_definition`, `find_implementations`, `get_folding_ranges`, `get_symbol_outline`, `call_hierarchy`, `type_hierarchy`, `selection_range`, `get_module_public_api`

### Refactoring (29 tools)
`rename_symbol`, `prepare_rename`, `extract_method`, `extract_variable`, `inline_variable`, `inline_method`, `inline_parameter`, `move_symbol`, `move_module`, `move_method`, `introduce_parameter`, `encapsulate_field`, `local_to_field`, `method_object`, `introduce_factory`, `module_to_package`, `generate_code`, `change_signature`, `argument_normalizer`, `argument_default_inliner`, `restructure`, `use_function`, `apply_code_action`, `organize_imports`, `expand_star_imports`, `relatives_to_absolutes`, `froms_to_imports`, `handle_long_imports`, `fix_module_names`

### Search (8 tools)
`find_constructors`, `search_symbols`, `structural_search`, `dead_code_detection`, `suggest_imports`, `autoimport_search`, `find_unused_imports`, `project_search`

### Metrics & Architecture (10 tools)
`code_metrics`, `get_type_coverage`, `get_coupling_metrics`, `get_module_dependencies`, `check_layer_violations`, `interface_conformance`, `extract_protocol`, `find_duplicated_code`, `find_errors_static`, `get_test_coverage_map`

### History & Change Management (6 tools)
`undo_refactoring`, `redo_refactoring`, `get_refactoring_history`, `begin_change_stack`, `commit_change_stack`, `rollback_change_stack`

### Composite & Utilities (8 tools)
`diff_preview`, `get_keyword_help`, `get_sub_definitions`, `simulate_execution`, `list_environments`, `restart_server`, `multi_project_rename`, `security_scan`

### Annotation Categories
- `_READONLY` — read-only, idempotent (analysis, navigation, search, metrics)
- `_ADDITIVE` — non-destructive mutations (organize_imports, apply_code_action, expand_star_imports, begin_change_stack, create_type_stubs)
- `_DESTRUCTIVE` — file-modifying refactorings (all default to `apply=False` preview mode)

## Common Agent Workflow Patterns

### Explore an unfamiliar file
1. `get_symbol_outline(file_path=<file>)` — get the symbol tree.
2. `get_type_info` on interesting symbols — confirm types and docs.
3. `goto_definition` — navigate to source of imported symbols.

### Find and fix a diagnostic error
1. `get_workspace_diagnostics()` — locate files with errors.
2. `get_diagnostics(file_path=<file>)` — inspect specific diagnostics.
3. `apply_code_action(file_path, line, character)` — apply the suggested fix.
4. `get_diagnostics(file_path=<file>)` again to confirm the error is gone.

### Safe rename
1. `prepare_rename` — verify the symbol is renameable.
2. `find_references` — confirm scope and count of usages.
3. `rename_symbol(apply=False, include_diff=True)` — preview all reference updates.
4. `rename_symbol(apply=True)` — apply.
5. `get_diagnostics` — verify.

### Add or clean up imports
1. `suggest_imports(symbol, file_path)` — get import statement options.
2. `organize_imports(file_path, apply=True)` — sort and deduplicate after insertion.

### Preview before applying
1. Generate edits from any refactoring tool with `apply=False`.
2. Pass the returned `edits` to `diff_preview(edits)` to review the unified diff.
3. Re-call the same tool with `apply=True` when the diff looks correct.

## Key Model Fields

- `TypeInfo`: `type_string`, `documentation`, `source` (pyright/jedi).
- `Diagnostic`: `file_path`, `range`, `severity`, `message`, `code`.
- `RefactorResult`: `edits` (list of `TextEdit`), `files_affected`, `applied`, `diagnostics_after`.
- `SymbolOutlineItem`: `name`, `kind`, `file_path`, `range`, `selection_range`, `children`.
- `DiffPreview`: `file_path`, `unified_diff`.

## Deep Historical Material

Historical implementation plans and prompts have been removed (available in git history).
