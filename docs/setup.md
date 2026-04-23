# Setup and Installation

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

Using `just` recipes:

```powershell
just build            # PyInstaller directory bundle
just build-release    # via scripts/build.ps1
just build-onefile    # single-file executable
```

## Validation And Local CI

Use the task runner when you want the supported command surface:

```powershell
just validate   # lint + pyright + unit tests
just ci         # mirrors .github/workflows/ci.yml
just --list     # show all available recipes
```

Direct commands:

- `python -m ruff check .` validates lint cleanliness.
- `python -m pyright .` validates the Pyright lane used by CI.
- `python -m mypy .` validates the strict mypy lane used by CI.
- `python -m pytest tests/unit/ -v` runs the unit suite.
- `.\scripts\test-integration.ps1` runs the integration suite against the supported test harness.

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
