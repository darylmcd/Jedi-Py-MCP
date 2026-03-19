# Python Refactor Domain Reference

Purpose: compact entry point for the Python refactor MCP domain.

## Core Files

- `src/python_refactor_mcp/server.py`
- `src/python_refactor_mcp/config.py`
- `src/python_refactor_mcp/models.py`
- `src/python_refactor_mcp/backends/pyright_lsp.py`
- `src/python_refactor_mcp/backends/jedi_backend.py`
- `src/python_refactor_mcp/backends/rope_backend.py`
- `src/python_refactor_mcp/tools/analysis.py`
- `src/python_refactor_mcp/tools/navigation.py`
- `src/python_refactor_mcp/tools/refactoring.py`
- `src/python_refactor_mcp/tools/search.py`
- `src/python_refactor_mcp/tools/composite.py`

## Tool Surface (35 tools)

### Analysis

| Tool | Returns | Notes |
|---|---|---|
| `find_references` | `ReferenceResult` | All usages + optional declaration. |
| `get_type_info` | `TypeInfo` | Type string, documentation, source (pyright/jedi). |
| `get_hover_info` | `TypeInfo` | Same as `get_type_info`; use for position-based hover. |
| `get_completions` | `list[CompletionItem]` | label, kind, insert_text, documentation. |
| `get_signature_help` | `SignatureInfo \| None` | label, parameters, active_parameter index. |
| `get_call_signatures_fallback` | `SignatureInfo \| None` | Jedi fallback signature help for dynamic call sites. |
| `get_document_highlights` | `list[DocumentHighlight]` | In-file text/read/write highlight ranges at a position. |
| `get_inlay_hints` | `list[InlayHint]` | Type/parameter inlay hints for a requested file range. |
| `get_semantic_tokens` | `list[SemanticToken]` | Decoded semantic token stream for symbol-classified analysis. |
| `get_diagnostics` | `list[Diagnostic]` | Per-file or workspace; supports severity_filter. |
| `get_workspace_diagnostics` | `list[DiagnosticSummary]` | Aggregate error/warning/hint counts per file, sorted by path. |

### Navigation

| Tool | Returns | Notes |
|---|---|---|
| `goto_definition` | `list[Location]` | Pyright primary, Jedi fallback. |
| `get_declaration` | `list[Location]` | Declaration/stub navigation; falls back to definition if unsupported. |
| `get_type_definition` | `list[Location]` | Type-definition navigation for aliases/protocol-heavy code. |
| `find_implementations` | `list[Location]` | Concrete implementations of abstract/protocol symbols. |
| `get_folding_ranges` | `list[FoldingRange]` | Foldable blocks for token-efficient chunking workflows. |
| `get_symbol_outline` | `list[SymbolOutlineItem]` | Hierarchical; omit file_path for full workspace scan. |
| `call_hierarchy` | `CallHierarchyResult` | Callers, callees, or both; configurable depth. |

### Refactoring

| Tool | Returns | Notes |
|---|---|---|
| `rename_symbol` | `RefactorResult` | rope rename; apply=False to preview. |
| `prepare_rename` | `PrepareRenameResult \| None` | Rename preflight; validates symbol/editable range first. |
| `smart_rename` | `RefactorResult` | Pyright reference scan + rope rename + post-apply validation. |
| `extract_method` | `RefactorResult` | Extract a text range into a new method. |
| `extract_variable` | `RefactorResult` | Extract an expression into a named variable. |
| `inline_variable` | `RefactorResult` | Inline a variable definition at all usages. |
| `move_symbol` | `RefactorResult` | Move a symbol to another file. |
| `introduce_parameter` | `RefactorResult` | Introduce a parameter and update call sites (preview/apply). |
| `encapsulate_field` | `RefactorResult` | Convert direct field access to encapsulated property accessors. |
| `apply_code_action` | `RefactorResult` | Apply any Pyright code action by title (or first available). |
| `organize_imports` | `RefactorResult` | Sort and deduplicate imports via Pyright source action. |

### Search

| Tool | Returns | Notes |
|---|---|---|
| `find_constructors` | `list[ConstructorSite]` | Call sites for a class constructor. |
| `search_symbols` | `list[SymbolInfo]` | Workspace symbol search across Pyright and Jedi, merged. |
| `structural_search` | `list[StructuralMatch]` | LibCST matcher-based AST pattern search. |
| `dead_code_detection` | `list[DeadCodeItem]` | Symbols with no detected references. |
| `suggest_imports` | `list[ImportSuggestion]` | Import statements for an unresolved symbol name. |

### Composite

| Tool | Returns | Notes |
|---|---|---|
| `diff_preview` | `list[DiffPreview]` | Unified diff of pending TextEdit objects; does not write. |

## Common Agent Workflow Patterns

### Explore an unfamiliar file
1. `get_symbol_outline(file_path=<file>)` — get the symbol tree.
2. `get_hover_info` on interesting symbols — confirm types and docs.
3. `goto_definition` — navigate to source of imported symbols.

### Find and fix a diagnostic error
1. `get_workspace_diagnostics()` — locate files with errors.
2. `get_diagnostics(file_path=<file>)` — inspect specific diagnostics.
3. `apply_code_action(file_path, line, character)` — apply the suggested fix.
4. `get_diagnostics(file_path=<file>)` again to confirm the error is gone.

### Safe rename
1. `find_references` — confirm scope and count of usages.
2. `diff_preview` — review generated edits before writing.
3. `smart_rename(apply=True)` — coordinated Pyright + rope rename with post-apply validation.

### Add or clean up imports
1. `suggest_imports(symbol, file_path)` — get import statement options.
2. `organize_imports(file_path, apply=True)` — sort and deduplicate after insertion.

### Navigate to implementations
1. `search_symbols(query)` — find the interface or abstract class.
2. `goto_definition` — jump to its definition.
3. `find_implementations` — discover all concrete implementations.

### Preview before applying
1. Generate edits from any refactoring tool with `apply=False`.
2. Pass the returned `edits` to `diff_preview(edits)` to review the unified diff.
3. Re-call the same tool with `apply=True` when the diff looks correct.

## Key Model Fields

- `TypeInfo`: `type_string`, `documentation`, `source` (pyright/jedi).
- `Diagnostic`: `file_path`, `range`, `severity`, `message`, `code`.
- `DiagnosticSummary`: `file_path`, `error_count`, `warning_count`, `total_count`.
- `SymbolOutlineItem`: `name`, `kind`, `file_path`, `range`, `selection_range`, `children`.
- `CompletionItem`: `label`, `kind`, `insert_text`, `documentation`.
- `SignatureInfo`: `label`, `parameters` (list of `ParameterInfo`), `active_parameter`.
- `RefactorResult`: `edits` (list of `TextEdit`), `files_affected`, `applied`, `diagnostics_after`.
- `DiffPreview`: `file_path`, `unified_diff`.
- `SymbolInfo`: `name`, `kind`, `file_path`, `range`, `container`.

## Recent Additions

The next-10 roadmap has been implemented. Highlights:

1. Safer rename flow via `prepare_rename` preflight and `rename_symbol`/`smart_rename` chaining.
2. Better navigation precision with `get_declaration` and `get_type_definition`.
3. Faster local reasoning via `get_document_highlights` and `get_folding_ranges`.
4. Richer semantic context via `get_inlay_hints` and `get_semantic_tokens`.
5. Expanded refactor primitives with `introduce_parameter` and `encapsulate_field`.
6. Dynamic-code fallback coverage with `get_call_signatures_fallback`.

Use the checklist in `ai_docs/domains/python-refactor/mcp-checklist.md` for all future MCP surface additions.

## Deep Historical Material

- `ai_docs/archive/python-refactor-mcp-prompt.md`
