# Surface detection — mcp-surface-audit 20260923-2310

| Field | Value |
|---|---|
| Target | `<repo>` @ `0f3f231` (clean tree at start) |
| Server id | `python-refactor` / `python-analysis` (same module, two tool profiles) |
| serverInfo | `{"name": "Python Refactor", "version": "0.5.0"}` |
| Stack | Python 3.14 / `mcp` SDK 2.1.1 `MCPServer` (FastMCP lineage) |
| Signals | `pyproject.toml` `[project.scripts] python-refactor-mcp = python_refactor_mcp.__main__:main`; `server.py` imports `mcp.server.mcpserver.MCPServer` |
| Launch (audit) | `.venv/Scripts/python.exe -m python_refactor_mcp <ws>` with `PYTHONPATH=src`, `PYRIGHT_LANGSERVER=.venv/Scripts/pyright-langserver.exe`, `PYTHON_REFACTOR_MCP_TOOL_PROFILE={refactoring,analysis}` |
| Launch (registered, `~/.claude.json`) | `python -m python_refactor_mcp <repo>` (PATH Python 3.14; editable install → same `src/`) |
| Transport | stdio, JSON-RPC via `mcp.client.stdio` + `ClientSession` (raw protocol; host fast path NOT used so wrong-type/missing-arg payloads reach the server unfiltered) |
| Backends | Pyright 1.1.411 (LSP), Jedi, rope 1.14 |
| Mode | `--mode=full`, `--output-mode=findings` |
| Workspaces | disposable copies only: `<scratch>/ws` (integration fixture + `src/audit.py` probe module), `<scratch>/ws2` (multi-root), `<scratch>/ws_repo` (copy of this repo's `src/`+`tests/`, 137 `.py`, timing pass) |
| Deep-harness delegation | N/A (not a Roslyn target) |

Environment note: `.venv` dist-info reports `python-refactor-mcp 0.4.1` while `src/__init__.py` and PATH-Python report `0.5.0` — stale editable metadata in the dev venv (code executed is HEAD `src/` in both cases).
