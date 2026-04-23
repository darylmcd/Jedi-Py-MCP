# Runtime
<!-- purpose: Verified environment, commands, and packaging facts for this repository. -->

Scope: verified environment, shell, task-runner, command, and packaging facts for this repository.

Primary command interface: `justfile`. Run `just --list` for the full command surface; use `just ci` as the local mirror of `.github/workflows/ci.yml`.

## Snapshot

| Item | Value |
|---|---|
| Repository | Jedi-Py-MCP |
| Repo class | Public |
| Primary language | Python 3.14+ |
| Build backend | Hatchling (`pyproject.toml`) |
| Entrypoints | `python -m python_refactor_mcp <workspace_root>`, `python-refactor-mcp <workspace_root>` |
| Host OS | Windows-first |
| Shell | PowerShell |
| Virtual environment | `.venv` |
| Hosted CI | `.github/workflows/ci.yml` — lint, Pyright, mypy, unit tests, integration tests on Python 3.14 (Windows) |
| Task runner | `justfile` |
| `rg` availability | Not installed |

## Canonical Runner

- `just --list`: lists every supported recipe.
- `just validate`: fast pre-push check (`ruff` + `pyright` + unit tests).
- `just ci`: exact local mirror of the hosted CI validate job.
- `just full`: full local validation surface, currently the same as `just ci`.

## Standard Commands

| Purpose | Direct command | Runner |
|---|---|---|
| Lint | `python -m ruff check .` | `just lint` |
| Type check (Pyright) | `python -m pyright .` | `just typecheck` |
| Type check (mypy) | `python -m mypy .` | `just typecheck-mypy` |
| Unit tests | `python -m pytest tests/unit/ -v` | `just test` |
| Integration tests | `./scripts/test-integration.ps1` | `just test-integration` |
| Local CI mirror | aggregate: lint + pyright + mypy + unit + integration | `just ci` |
| Build executable (directory bundle) | `./scripts/build.ps1` | `just build-release` |
| Build executable (one-file) | `./scripts/build.ps1 -OneFile` | `just build-onefile` |
| Run server | `python -m python_refactor_mcp <workspace_root>` | `just run <workspace_root>` |

## Local Run

- Install from source: `python -m pip install .`
- Install for development: `python -m pip install -e ".[dev]"`
- Install with build tooling: `python -m pip install -e ".[build]"`
- Start the stdio server: `python -m python_refactor_mcp <workspace_root>`
- Check the CLI entrypoint: `python -m python_refactor_mcp --version`

## Config And Environment

| Item | Type | Notes |
|---|---|---|
| `workspace_root` | required CLI arg | Workspace analyzed by the MCP server |
| `PYRIGHT_LANGSERVER` | env var | Overrides the default `pyright-langserver` executable |
| `VIRTUAL_ENV` | env var | Interpreter discovery fallback |
| `pyrightconfig.json` | workspace file | Optional Pyright project config, discovered from the workspace root |
| `.venv` / `venv` | workspace directories | Preferred interpreter discovery locations |
| `manifest.json` | repo root file | Manifest metadata for clients and packaging |

Interpreter discovery order in `config.py`: `.venv` -> `venv` -> Poetry virtualenv path from `pyproject.toml` -> `VIRTUAL_ENV` -> `python3` -> `python`.

## Packaging And Distribution

- Python package metadata lives in `pyproject.toml`.
- Editable and non-editable installs are supported from source.
- The console script entrypoint is `python-refactor-mcp`.
- Windows executable packaging is handled by `scripts/build.ps1` and `build.bat`.
- The packaged executable does not bundle a separate Pyright runtime; the target environment still needs the `pyright` Python package so `pyright-langserver` can be resolved at runtime.

## CI Summary

1. Create `.venv`.
2. Install `.[dev,build]`.
3. Run `ruff`.
4. Run `pyright`.
5. Run `mypy`.
6. Run unit tests.
7. Run integration tests.

## Policy Boundaries

- Validation and merge-gating policy is owned by `../CI_POLICY.md`.
- Branch, worktree, and PR execution policy is owned by `workflow.md`.

## Update Checklist

- Command or recipe changed -> update this file and the runner in the same change.
- CI workflow changed -> update `just ci` and this file in the same change.
- New required environment variable or config file -> add it here.
- New packaging or distribution path -> document the command and artifact here.
