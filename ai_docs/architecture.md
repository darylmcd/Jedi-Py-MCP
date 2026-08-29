# Architecture
<!-- purpose: Compact system architecture reference — backends, tool surface, runtime flow. -->

Purpose: compact architecture reference for AI contributors.

## Code Map

| Domain / Feature | Source path(s) | Key types | Tests |
|---|---|---|---|
| Server lifecycle & tool registration | `src/python_refactor_mcp/server.py`, `src/python_refactor_mcp/tool_registry.py` | `TOOL_RECORDS`, `_tool_error_boundary` | `tests/unit/test_server.py`, `tests/contract/` |
| Config & workspace discovery | `src/python_refactor_mcp/config.py` | `WorkspaceRegistry`, `MultiWorkspaceContext` | `tests/unit/` |
| Shared response models | `src/python_refactor_mcp/models.py` | `TypeInfo`, `Diagnostic`, `RefactorResult`, `SymbolOutlineItem`, `DiffPreview` | `tests/unit/` |
| Error types | `src/python_refactor_mcp/errors.py` | `BackendError` subclasses | `tests/unit/` |
| Pyright LSP backend | `src/python_refactor_mcp/backends/pyright_lsp.py` | `PyrightLSPClient` | `tests/unit/`, `tests/integration/` |
| Jedi backend | `src/python_refactor_mcp/backends/jedi_backend.py` | `JediBackend` | `tests/unit/` |
| rope backend | `src/python_refactor_mcp/backends/rope_backend.py` | `RopeBackend` | `tests/unit/` |
| Shared backend threading helper | `src/python_refactor_mcp/backends/_threading.py` | `run_in_thread` | `tests/unit/` |
| LibCST apply foundation | `src/python_refactor_mcp/util/cst_apply.py` | CST apply/codemod helpers | `tests/unit/` |
| Tool orchestration | `src/python_refactor_mcp/tools/analysis/`, `.../navigation/`, `.../refactoring/`, `.../search/`, `.../metrics/`, `.../composite.py` | per-category tool implementations | `tests/unit/`, `tests/contract/` |
| Shared LSP/diff/path utilities | `src/python_refactor_mcp/util/` | LSP client, diff, path helpers | `tests/unit/` |

## Entry points

| Entry point | Starts |
|---|---|
| `src/python_refactor_mcp/__main__.py` | CLI entry — parses the optional `workspace_root` argument, calls `server.run_server()` |
| `python-refactor-mcp` console script (`pyproject.toml`) | Installed-package equivalent of `__main__.py` |

## Backend Roles

| Backend | Role | Fallback |
|---------|------|---------|
| Pyright (`pyright-langserver`) | Type-aware semantic analysis, diagnostics, navigation, code actions | None — primary for typed analysis |
| Jedi | Dynamic fallback analysis, completions, environment discovery | Used when Pyright unavailable or for dynamic code |
| rope | Mutation-safe refactoring edits, rename, extract, move | None — primary for AST-level mutations |

## Tool Surface

See `domains/python-refactor/reference.md` for the categorized tool surface and the authoritative tool count. Do not duplicate the count here — it drifts.

## Runtime Flow

1. Optional CLI `workspace_root` pre-warms one workspace; otherwise the first path-bearing tool call discovers its project root.
2. `config.py` resolves the interpreter and `pyrightconfig.json` for each discovered workspace.
3. FastMCP lifespan initializes all three backends and a `MultiWorkspaceContext`.
4. Incoming tool calls are routed through `tools/` orchestration modules.
5. Refactoring tools return `TextEdit` lists by default (`apply=False`).
6. When `apply=True`, edits are written atomically and `diagnostics_after` is returned.

## Key Model Types

| Model | Fields |
|-------|--------|
| `TypeInfo` | `type_string`, `documentation`, `source` (pyright/jedi) |
| `Diagnostic` | `file_path`, `range`, `severity`, `message`, `code` |
| `RefactorResult` | `edits`, `files_affected`, `applied`, `diagnostics_after` |
| `SymbolOutlineItem` | `name`, `kind`, `file_path`, `range`, `selection_range`, `children` |
| `DiffPreview` | `file_path`, `unified_diff` |

## Known Gaps

- `list_environments` may return empty results depending on virtualenv layout (known Jedi discovery limitation).
- Pyright diagnostics on lines with `# type: ignore` may still surface in tool results (LSP filtering limitation).
