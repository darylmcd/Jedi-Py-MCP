# Jedi-Py-MCP

[![CI](https://github.com/darylmcd/Jedi-Py-MCP/actions/workflows/ci.yml/badge.svg)](https://github.com/darylmcd/Jedi-Py-MCP/actions/workflows/ci.yml)

Jedi-Py-MCP is a production-oriented Python MCP server for analysis and refactoring. It combines three backends behind one MCP tool surface:

- Pyright for semantic analysis, references, diagnostics, definitions, and call hierarchy.
- Jedi for fallback analysis in dynamic or weakly typed code.
- rope for edit generation and refactoring-safe file mutations.

Current implementation status: Stage 6 complete.

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

## Tool Reference

| Tool | Purpose | Returns |
|---|---|---|
| `find_references` | Find references for a symbol at a source location. | `ReferenceResult` |
| `get_type_info` | Resolve type information for an expression or symbol. | `TypeInfo` |
| `get_hover_info` | Return hover-style type and documentation metadata for a symbol. | `TypeInfo` |
| `get_completions` | Return completion candidates for a cursor location. | `list[CompletionItem]` |
| `get_signature_help` | Return active signature and parameter help at a call site. | `SignatureInfo \| None` |
| `get_diagnostics` | Return Pyright diagnostics for a file or workspace. | `list[Diagnostic]` |
| `get_workspace_diagnostics` | Summarize diagnostics per file across the workspace. | `list[DiagnosticSummary]` |
| `goto_definition` | Navigate to symbol definitions. | `list[Location]` |
| `find_implementations` | Navigate to concrete implementation locations. | `list[Location]` |
| `get_symbol_outline` | Return a hierarchical symbol outline for a file or workspace. | `list[SymbolOutlineItem]` |
| `call_hierarchy` | Return callers and callees for a symbol. | `CallHierarchyResult` |
| `rename_symbol` | Generate or apply a rope rename. | `RefactorResult` |
| `smart_rename` | Run Pyright reference discovery plus rope rename and validation. | `RefactorResult` |
| `extract_method` | Extract a selected block into a method. | `RefactorResult` |
| `extract_variable` | Extract an expression into a variable. | `RefactorResult` |
| `inline_variable` | Inline a variable definition and usages. | `RefactorResult` |
| `move_symbol` | Move a symbol between files. | `RefactorResult` |
| `apply_code_action` | Preview or apply a Pyright code action at a source position. | `RefactorResult` |
| `organize_imports` | Preview or apply import organization for a file. | `RefactorResult` |
| `find_constructors` | Locate constructor call sites for a class. | `list[ConstructorSite]` |
| `search_symbols` | Search workspace symbols by name across semantic backends. | `list[SymbolInfo]` |
| `structural_search` | Search Python code using LibCST matcher expressions. | `list[StructuralMatch]` |
| `dead_code_detection` | Identify likely dead symbols and unused code. | `list[DeadCodeItem]` |
| `suggest_imports` | Suggest import statements for unresolved symbols. | `list[ImportSuggestion]` |
| `diff_preview` | Build unified diffs for pending text edits. | `list[DiffPreview]` |

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