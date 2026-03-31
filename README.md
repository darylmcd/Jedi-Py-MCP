# Jedi-Py-MCP

[![CI](https://github.com/darylmcd/Jedi-Py-MCP/actions/workflows/ci.yml/badge.svg)](https://github.com/darylmcd/Jedi-Py-MCP/actions/workflows/ci.yml)

Jedi-Py-MCP is a production-oriented Python MCP server for analysis and refactoring. It combines three backends behind one MCP tool surface:

- Pyright for semantic analysis, references, diagnostics, definitions, and call hierarchy.
- Jedi for fallback analysis in dynamic or weakly typed code.
- rope for edit generation and refactoring-safe file mutations.

Current implementation status: Stage 6 complete.

## Features

- **87 MCP tools** spanning analysis, navigation, refactoring, search, metrics, history management, and utilities.
- **Three-backend architecture**: Pyright (semantic/LSP), Jedi (dynamic fallback), and rope (refactoring engine).
- **Safe refactoring workflow**: all mutation tools default to preview mode (`apply=False`) and require explicit opt-in to write changes.
- **Post-refactor validation**: refactoring results include `diagnostics_after` when edits are applied, so you can verify correctness immediately.
- **Composite workflows**: `smart_rename` coordinates Pyright reference discovery with rope rename; `diff_preview` generates unified diffs for any pending edits.
- **Workspace-aware**: automatic Python interpreter and `pyrightconfig.json` discovery from the workspace root.
- **Structured output**: all tools return typed Pydantic models for reliable downstream consumption.

## Requirements

- Python 3.14+
- Windows-first workflow with PowerShell examples
- A Python environment that has the `pyright` package installed so `pyright-langserver` is available on PATH

## Installation

Install the server from source:

```powershell
python -m pip install .
```

Install with development tools:

```powershell
python -m pip install -e ".[dev]"
```

Install with build tooling:

```powershell
python -m pip install -e ".[build]"
```

Install from requirements:

```powershell
python -m pip install -r requirements.txt
```

The `pyright` requirement installs the `pyright-langserver` executable used by the server.

## Executable Build

Build a Windows executable with PyInstaller:

```powershell
.\scripts\build.ps1
```

From Command Prompt (or when you prefer a batch entry point):

```bat
.\build.bat
```

Optional flags:

- `-OneFile` builds a single executable instead of a directory bundle.
- `-Clean` removes previous `build/`, `dist/`, and spec outputs before packaging.

The packaged executable contains the Python MCP server only. It does not bundle Node.js or a separate Pyright runtime. Users still need the `pyright` Python package installed so `pyright-langserver` can be resolved at runtime.

## Running The Server

Start the stdio server against a workspace:

```powershell
python -m python_refactor_mcp C:\path\to\python\project
```

Check the CLI version:

```powershell
python -m python_refactor_mcp --version
```

## MCP Client Configuration

### VS Code Copilot

```json
{
	"mcpServers": {
		"python-refactor": {
			"command": "python",
			"args": ["-m", "python_refactor_mcp", "C:/path/to/python/project"]
		}
	}
}
```

### Claude Desktop

```json
{
	"mcpServers": {
		"python-refactor": {
			"command": "python",
			"args": ["-m", "python_refactor_mcp", "C:/path/to/python/project"]
		}
	}
}
```

### Packaged Executable

```json
{
	"mcpServers": {
		"python-refactor": {
			"command": "C:/path/to/dist/python-refactor-mcp/python-refactor-mcp.exe",
			"args": ["C:/path/to/python/project"]
		}
	}
}
```

## Configuration

Workspace discovery is automatic and happens from the workspace root argument.

Python interpreter discovery order:

1. `.venv`
2. `venv`
3. Poetry virtualenv path from `pyproject.toml`
4. `VIRTUAL_ENV`
5. System `python3`
6. System `python`

Other runtime discovery:

- `pyrightconfig.json` is detected from the workspace root.
- `PYRIGHT_LANGSERVER` can override the default `pyright-langserver` executable.
- Rope preferences are initialized from server defaults in `config.py`.

## Usage Examples

### Example 1: Find all references to a symbol

**Prompt:** "Find all usages of the `discover_config` function in the project."

**Tool call:**
```json
{
  "tool": "find_references",
  "arguments": {
    "file_path": "src/python_refactor_mcp/config.py",
    "line": 42,
    "character": 4,
    "include_context": true
  }
}
```

**Expected output:** A `ReferenceResult` containing each location where `discover_config` is referenced, with file path, line, character, and optional surrounding context lines. The `source` field indicates which backend (pyright or jedi) resolved the references.

### Example 2: Preview a rename before applying

**Prompt:** "Rename the `_get_app_context` helper to `_resolve_context` but show me the diff first."

**Tool call (step 1 — preview):**
```json
{
  "tool": "smart_rename",
  "arguments": {
    "file_path": "src/python_refactor_mcp/server.py",
    "line": 141,
    "character": 4,
    "new_name": "_resolve_context",
    "apply": false
  }
}
```

**Expected output:** A `RefactorResult` with `applied=false`, a list of `TextEdit` objects showing every file and range that would change, and `files_affected` count. You can then pass the edits to `diff_preview` for a unified diff view, and finally re-run with `apply=true` to commit the changes.

### Example 3: Detect dead code in a module

**Prompt:** "Check `src/python_refactor_mcp/util/paths.py` for unused symbols."

**Tool call:**
```json
{
  "tool": "dead_code_detection",
  "arguments": {
    "file_path": "src/python_refactor_mcp/util/paths.py"
  }
}
```

**Expected output:** A list of `DeadCodeItem` objects, each containing the symbol name, kind (function, class, variable), file path, line number, and a confidence indicator. Symbols that are exported or referenced elsewhere will not appear.

### Example 4: Organize imports and apply

**Prompt:** "Clean up the imports in server.py."

**Tool call:**
```json
{
  "tool": "organize_imports",
  "arguments": {
    "file_path": "src/python_refactor_mcp/server.py",
    "apply": true
  }
}
```

**Expected output:** A `RefactorResult` with `applied=true`, the list of `TextEdit` objects that were written, and `diagnostics_after` showing any remaining Pyright diagnostics in the file.

### Example 5: Error handling — invalid file path

**Prompt:** "Get diagnostics for a file that doesn't exist."

**Tool call:**
```json
{
  "tool": "get_diagnostics",
  "arguments": {
    "file_path": "nonexistent/module.py"
  }
}
```

**Expected output:** A tool error (`isError: true`) with a message indicating the file was not found, allowing the caller to self-correct by providing a valid path.

## Tool Reference

**Analysis (16)**

| Tool | Purpose | Returns |
|---|---|---|
| `find_references` | Find all references to a symbol. | `ReferenceResult` |
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

**Navigation (10)**

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

**Refactoring (29)**

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
| `expand_star_imports` | Expand `import *` to explicit names. | `RefactorResult` |
| `relatives_to_absolutes` | Convert relative imports to absolute. | `RefactorResult` |
| `froms_to_imports` | Convert `from X import Y` to `import X.Y` form. | `RefactorResult` |
| `handle_long_imports` | Break long import lines into shorter form. | `RefactorResult` |
| `fix_module_names` | Fix incorrect module references across the workspace. | `RefactorResult` |

**Search (8)**

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

**Metrics & Architecture (10)**

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

**History & Change Management (6)**

| Tool | Purpose | Returns |
|---|---|---|
| `undo_refactoring` | Undo the last N refactoring operations via Rope history. | `RefactorResult` |
| `redo_refactoring` | Redo the last N undone refactoring operations. | `RefactorResult` |
| `get_refactoring_history` | Return the current Rope refactoring history stack. | `list[HistoryEntry]` |
| `begin_change_stack` | Start a Rope ChangeStack for grouping refactorings. | `str` |
| `commit_change_stack` | Commit all changes in the current ChangeStack. | `RefactorResult` |
| `rollback_change_stack` | Roll back all changes in the current ChangeStack. | `str` |

**Composite & Utilities (8)**

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

Refactoring tools default to returning `TextEdit` data. Set `apply=True` to write changes to disk and return post-change diagnostics.

## Architecture

```text
MCP Client
		|
		v
FastMCP Server (stdio)
		|
		+--> Analysis tools ----------> Pyright LSP client ----------> pyright-langserver
		|
		+--> Fallback analysis -------> Jedi backend
		|
		+--> Refactoring tools -------> rope backend
		|
		+--> Composite workflows -----> Pyright + rope validation loop
```

## Troubleshooting

### `pyright-langserver` not found

- Install the `pyright` package in the same environment as the server.
- Verify `python -m pyright --version` succeeds.
- Set `PYRIGHT_LANGSERVER` if the executable is in a non-standard location.

### Virtual environment not detected

- Pass the intended workspace root, not a nested source directory.
- Confirm the venv is named `.venv` or `venv`, or expose it via `VIRTUAL_ENV`.
- If using Poetry, ensure the configured virtualenv path is present in `pyproject.toml`.

### Build script fails

- Install build dependencies with `python -m pip install -e ".[build]"` or `python -m pip install -r requirements.txt`.
- Run the script from PowerShell.
- Use `-Clean` to remove stale PyInstaller artifacts.

### Refactoring applies edits but diagnostics remain

- Inspect the returned `diagnostics_after` field in the refactor result.
- Validate the target project with Pyright directly to confirm whether the issue is pre-existing.

## Development And Validation

```powershell
python -m ruff check .
python -m pyright .
python -m mypy .
python -m pytest tests/unit/ -v
./scripts/test-integration.ps1
```

## Repository Map

- `src/python_refactor_mcp/server.py`: MCP lifecycle and tool registration
- `src/python_refactor_mcp/config.py`: workspace and runtime discovery
- `src/python_refactor_mcp/models.py`: shared structured response models
- `src/python_refactor_mcp/backends/`: Pyright, Jedi, and rope integrations
- `src/python_refactor_mcp/tools/`: tool orchestration layer
- `src/python_refactor_mcp/util/`: LSP, path, and diff helpers
- `tests/unit/`: unit test suite
- `tests/integration/`: end-to-end MCP and backend coverage
- `ai_docs/`: canonical repo workflow and policy docs

## Privacy Policy

This server runs entirely on your local machine. It does not collect telemetry, make network requests, or transmit any data externally. See [PRIVACY.md](PRIVACY.md) for the full policy.

## Support

- **Issues:** https://github.com/darylmcd/Jedi-Py-MCP/issues
- **Discussions:** https://github.com/darylmcd/Jedi-Py-MCP/discussions