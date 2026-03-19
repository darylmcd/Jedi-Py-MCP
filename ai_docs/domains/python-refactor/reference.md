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

## Tool Surface (25 tools)

### Analysis

| Tool | Returns | Notes |
|---|---|---|
| `find_references` | `ReferenceResult` | All usages + optional declaration. |
| `get_type_info` | `TypeInfo` | Type string, documentation, source (pyright/jedi). |
| `get_hover_info` | `TypeInfo` | Same as `get_type_info`; use for position-based hover. |
| `get_completions` | `list[CompletionItem]` | label, kind, insert_text, documentation. |
| `get_signature_help` | `SignatureInfo \| None` | label, parameters, active_parameter index. |
| `get_diagnostics` | `list[Diagnostic]` | Per-file or workspace; supports severity_filter. |
| `get_workspace_diagnostics` | `list[DiagnosticSummary]` | Aggregate error/warning/hint counts per file, sorted by path. |

### Navigation

| Tool | Returns | Notes |
|---|---|---|
| `goto_definition` | `list[Location]` | Pyright primary, Jedi fallback. |
| `find_implementations` | `list[Location]` | Concrete implementations of abstract/protocol symbols. |
| `get_symbol_outline` | `list[SymbolOutlineItem]` | Hierarchical; omit file_path for full workspace scan. |
| `call_hierarchy` | `CallHierarchyResult` | Callers, callees, or both; configurable depth. |

### Refactoring

| Tool | Returns | Notes |
|---|---|---|
| `rename_symbol` | `RefactorResult` | rope rename; apply=False to preview. |
| `smart_rename` | `RefactorResult` | Pyright reference scan + rope rename + post-apply validation. |
| `extract_method` | `RefactorResult` | Extract a text range into a new method. |
| `extract_variable` | `RefactorResult` | Extract an expression into a named variable. |
| `inline_variable` | `RefactorResult` | Inline a variable definition at all usages. |
| `move_symbol` | `RefactorResult` | Move a symbol to another file. |
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

## Next 10 High-Value Unexposed Picks

These are prioritized additions that are not currently exposed as MCP tools but are available via underlying backends (Pyright/Jedi/rope).

1. `get_declaration` (Pyright `textDocument/declaration`)
	- Why: agent can jump to stubs/interfaces when definition points to implementation or import glue.
2. `get_type_definition` (Pyright `textDocument/typeDefinition`)
	- Why: critical for understanding concrete runtime type behind aliases/protocol-heavy code.
3. `get_document_highlights` (Pyright `textDocument/documentHighlight`)
	- Why: fast local symbol usage clustering in-file before expensive workspace scans.
4. `prepare_rename` (Pyright `textDocument/prepareRename`)
	- Why: preflight safety check before rename/edit operations; reduces failed refactors.
5. `get_inlay_hints` (Pyright `textDocument/inlayHint`)
	- Why: exposes inferred type/parameter names to improve agent reasoning and code review output.
6. `get_semantic_tokens` (Pyright `textDocument/semanticTokens/full`)
	- Why: enables robust symbol-kind-aware analysis and richer code understanding.
7. `get_folding_ranges` (Pyright `textDocument/foldingRange`)
	- Why: helps chunk large files into review/refactor windows for token-efficient planning.
8. `get_call_signatures_fallback` (Jedi `Script.get_signatures`)
	- Why: fallback when Pyright signature help is absent in dynamic code.
9. `introduce_parameter` (rope `refactor.introduce_parameter`)
	- Why: high-value API evolution primitive for agents doing compatibility-preserving refactors.
10. `encapsulate_field` (rope `refactor.encapsulate_field`)
	- Why: converts direct attribute access into managed property access for safer staged refactors.

Use the implementation and quality checklist in `ai_docs/domains/python-refactor/mcp-checklist.md` before exposing any new tool.

## Deep Historical Material

- `ai_docs/archive/python-refactor-mcp-prompt.md`
