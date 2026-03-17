# Jedi-Py-MCP

`Jedi-Py-MCP` is a Python MCP server for code analysis and refactoring that combines:

- Pyright for type-aware semantic analysis
- Jedi for dynamic-analysis fallback
- rope for mutation-safe refactoring edits

Current implementation status: Stage 3 complete (backend layer implemented and unit-tested).

## Installation

Requirements:
- Python 3.13+

Install in editable mode with development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

## Run the Server

Start the MCP server over stdio and pass a workspace root:

```powershell
python -m python_refactor_mcp C:\path\to\python\project
```

## MCP Client Configuration Example

Example JSON snippet for an MCP client configuration:

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

## Development Commands

```powershell
python -m ruff check .
python -m pyright .
python -m mypy .
python -m pytest tests/unit/ -v
```

## Repository Map

- `src/python_refactor_mcp/server.py`: FastMCP app lifecycle and tool registration
- `src/python_refactor_mcp/config.py`: workspace and runtime discovery
- `src/python_refactor_mcp/models.py`: shared output models
- `src/python_refactor_mcp/backends/`: Pyright, Jedi, and rope backend implementations
- `src/python_refactor_mcp/tools/`: tool-level orchestrators (placeholder implementations pending Stage 4)
- `src/python_refactor_mcp/util/`: LSP and diff helper utilities
- `tests/unit/`: unit test suite
- `ai_docs/`: canonical AI workflow and policy docs

## AI Session Flow

For AI-assisted sessions, start with `AGENTS.md` and follow the canonical docs chain in order:

1. `.github/copilot-instructions.md`
2. `ai_docs/quickstart.md`
3. `ai_docs/README.md`
4. `ai_docs/runtime.md`
5. `ai_docs/workflow.md`
6. `CI_POLICY.md`
7. `ai_docs/backlog.md`