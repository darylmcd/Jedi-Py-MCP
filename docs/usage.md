# Usage

## Running The Server

Start the stdio server against a workspace:

```powershell
python -m python_refactor_mcp C:\path\to\python\project
```

Check the CLI version:

```powershell
python -m python_refactor_mcp --version
```

Or via `just`:

```powershell
just run C:\path\to\python\project
```

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

**Tool call (step 1 -- preview):**
```json
{
  "tool": "rename_symbol",
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

### Example 5: Error handling -- invalid file path

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

Refactoring tools default to returning `TextEdit` data. Set `apply=True` to write changes to disk and return post-change diagnostics.
