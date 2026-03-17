# Runtime

Scope: verified environment, shell, tool, editor, and integration facts for this repository.

## Snapshot

| Item | Value |
|---|---|
| Repository | Jedi-Py-MCP |
| Implementation status | Stage 6 complete |
| Entrypoint | python -m python_refactor_mcp <workspace_root> |
| Host OS | Windows |
| Shell | PowerShell |
| Virtual environment | .venv |
| Hosted CI | Not configured |
| rg availability | Not installed |

## Standard Commands

| Purpose | Command |
|---|---|
| Lint | python -m ruff check . |
| Type check (Pyright) | python -m pyright . |
| Type check (mypy) | python -m mypy . |
| Unit tests | python -m pytest tests/unit/ -v |
| Integration tests | python -m pytest tests/integration/ -v |
| Build executable | ./scripts/build.ps1 |

## Assumptions

- Treat bootstrap docs as the source of truth for agent behavior in this repo.
- Do not assume external CLIs such as GitHub CLI, Node.js toolchains, Python toolchains, browsers, or MCP servers are available unless they are verified in the repo or current environment.
- The `pyright` Python package provides the `pyright-langserver` executable required by the server and packaged build.
- If a future change introduces required tooling, record the verified command surface here.

## Update Checklist

- Shells available
- Language runtimes available
- Required CLIs and whether they are repo-managed or system-managed
- Test, lint, and build entry points
- External services or credentials assumptions
- Host-specific constraints that affect agent behavior