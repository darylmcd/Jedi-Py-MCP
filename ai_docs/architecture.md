# Architecture

Purpose: compact architecture reference for AI contributors.

## System Layout

| Path | Role |
|------|------|
| `src/python_refactor_mcp/__main__.py` | Entry point |
| `src/python_refactor_mcp/server.py` | Server lifecycle, tool registration (87 tools) |
| `src/python_refactor_mcp/config.py` | Runtime and workspace discovery |
| `src/python_refactor_mcp/models.py` | Shared Pydantic response models |
| `src/python_refactor_mcp/backends/` | Pyright LSP, Jedi, and rope integrations |
| `src/python_refactor_mcp/tools/` | Tool orchestration by domain |
| `src/python_refactor_mcp/util/` | LSP client, diff helpers, shared protocols |

## Backend Roles

| Backend | Role | Fallback |
|---------|------|---------|
| Pyright (`pyright-langserver`) | Type-aware semantic analysis, diagnostics, navigation, code actions | None — primary for typed analysis |
| Jedi | Dynamic fallback analysis, completions, environment discovery | Used when Pyright unavailable or for dynamic code |
| rope | Mutation-safe refactoring edits, rename, extract, move | None — primary for AST-level mutations |

## Tool Surface

87 tools in 7 categories: Analysis (16), Navigation (10), Refactoring (29), Search (8), Metrics & Architecture (10), History & Change Management (6), Composite & Utilities (8).

See `domains/python-refactor/reference.md` for the full categorized list.

## Runtime Flow

1. CLI arg provides `workspace_root`; `config.py` resolves interpreter and `pyrightconfig.json`.
2. FastMCP lifespan initializes all three backends and a `MultiWorkspaceContext`.
3. Incoming tool calls are routed through `tools/` orchestration modules.
4. Refactoring tools return `TextEdit` lists by default (`apply=False`).
5. When `apply=True`, edits are written atomically and `diagnostics_after` is returned.

## Key Model Types

| Model | Fields |
|-------|--------|
| `TypeInfo` | `type_string`, `documentation`, `source` (pyright/jedi) |
| `Diagnostic` | `file_path`, `range`, `severity`, `message`, `code` |
| `RefactorResult` | `edits`, `files_affected`, `applied`, `diagnostics_after` |
| `SymbolOutlineItem` | `name`, `kind`, `file_path`, `range`, `selection_range`, `children` |
| `DiffPreview` | `file_path`, `unified_diff` |

## Known Gaps

- `change_signature` strips Python 3 type annotations during normalization (rope `ArgumentNormalizer` upstream limitation). Documented in `backends/rope_backend.py`.
- `list_environments` may return empty results depending on virtualenv layout (known Jedi discovery limitation).
- Pyright diagnostics on lines with `# type: ignore` may still surface in tool results (LSP filtering limitation).
