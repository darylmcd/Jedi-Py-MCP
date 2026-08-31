# Runtime
<!-- purpose: Verified environment, commands, and packaging facts for this repository. -->

Scope: verified environment, shell, task-runner, command, and packaging facts for this repository.

Primary command interface: `justfile`. Run `just --list` for the full command surface; use `just ci` as the local mirror of `.github/workflows/ci.yml`.

## Snapshot

| Item | Value |
|---|---|
| Repository | Jedi-Py-MCP |
| Repo class | Private |
| Primary language | Python 3.14+ |
| Build backend | Hatchling (`pyproject.toml`) |
| Entrypoints | `python -m python_refactor_mcp [workspace_root]`, `python-refactor-mcp [workspace_root]` |
| Default tool profile | `refactoring` (73 advertised; profile budget is 80) |
| Host OS | Windows-first |
| Shell | PowerShell |
| Virtual environment | `.venv` |
| Hosted CI | `.github/workflows/ci.yml` — changelog validation, lint, Pyright, mypy, unit + contract tests, integration tests on Python 3.14 (Windows) |
| Task runner | `justfile` |
| `rg` availability | Installed on PATH |

## Canonical Runner

- `just --list`: lists every supported recipe.
- `just validate`: fast pre-push check (changelog fragments + `ruff` + `pyright` + unit + contract tests).
- `just ci`: exact local mirror of the hosted CI validate job.
- `just full`: full local validation surface, currently the same as `just ci`.

## Standard Commands

| Purpose | Direct command | Runner |
|---|---|---|
| Changelog fragments | `python scripts/changelog_fragments.py` | `just changelog-check` |
| Lint | `python -m ruff check .` | `just lint` |
| Type check (Pyright) | `python -m pyright .` | `just typecheck` |
| Type check (mypy) | `python -m mypy .` | `just typecheck-mypy` |
| Unit + contract tests | `python -m pytest tests/unit/ tests/contract/ -v` | `just test` |
| Integration tests | `./scripts/test-integration.ps1` | `just test-integration` |
| Local CI mirror | aggregate: changelog + lint + pyright + mypy + unit + integration | `just ci` |
| Build executable (directory bundle) | `./scripts/build.ps1` | `just build-release` |
| Build executable (one-file) | `./scripts/build.ps1 -OneFile` | `just build-onefile` |
| Run server | `python -m python_refactor_mcp [workspace_root]` | `just run <workspace_root>` |
| Bump + reinstall | `python scripts/bump_reinstall.py patch --target-python python` | `just bump-reinstall patch` |
| Reinstall current release | `python scripts/bump_reinstall.py --reinstall-only --target-python python` | `just reinstall` |

## Local Run

- Install from source: `python -m pip install .`
- Install the locked development environment: `uv sync --locked --all-extras`
- Install for development without uv: `python -m pip install -e ".[dev]"`
- Install with build tooling: `python -m pip install -e ".[build]"`
- Start the stdio server: `python -m python_refactor_mcp [workspace_root]`
- Select the read-only analysis surface before startup: `$env:PYTHON_REFACTOR_MCP_TOOL_PROFILE = "analysis"` (PowerShell), then start normally.
- Check the CLI entrypoint: `python -m python_refactor_mcp --version`
- Bump `major`, `minor`, `patch`, or to an explicit greater release; refresh `uv.lock`; reinstall the exact locked runtime dependencies and editable package into the client interpreter; run `pip check`; then verify its CLI: `just bump-reinstall patch [target_python]`. The default target is `python` on PATH because that is the command in `manifest.json` and the local Claude MCP configuration. Pre-install failures restore release files; failures after installation starts retain them so source metadata cannot contradict a partially updated interpreter.
- Repair a failed/removed install or refresh the current locked release without changing version metadata: `just reinstall [target_python]`.

## Config And Environment

| Item | Type | Notes |
|---|---|---|
| `workspace_root` | optional CLI arg | Pre-warms that workspace; when omitted, path-bearing tool requests discover project roots dynamically |
| `PYRIGHT_LANGSERVER` | env var | Overrides the default `pyright-langserver` executable |
| `PYTHON_REFACTOR_MCP_TOOL_PROFILE` | env var | Advertised surface: `refactoring` (default, 73) or `analysis` (56); each stays below the reliability budget of 80 and their union covers the 106-tool catalog |
| `MAX_WORKSPACES` | env var | Positive integer workspace cache limit; defaults to `3` and fails startup with a configuration error when invalid |
| `VIRTUAL_ENV` | env var | Interpreter discovery fallback |
| `pyrightconfig.json` | workspace file | Optional Pyright project config, discovered from the workspace root |
| `.venv` / `venv` | workspace directories | Preferred interpreter discovery locations |
| `manifest.json` | repo root file | Manifest metadata for clients and packaging |

Interpreter discovery order in `config.py`: `.venv` -> `venv` -> Poetry virtualenv path from `pyproject.toml` -> `VIRTUAL_ENV` -> `python3` -> `python`.

## Packaging And Distribution

- Python package metadata lives in `pyproject.toml`.
- Release versions are synchronized across `pyproject.toml`, `src/python_refactor_mcp/__init__.py`, and `manifest.json`; `scripts/bump_reinstall.py` validates and atomically consumes `changelog.d/*.md` into a dated release section, then refreshes the derived `uv.lock` entry.
- Editable and non-editable installs are supported from source.
- The console script entrypoint is `python-refactor-mcp`.
- Windows executable packaging is handled by `scripts/build.ps1` and `build.bat`.
- The packaged executable does not bundle a separate Pyright runtime; the target environment still needs the `pyright` Python package so `pyright-langserver` can be resolved at runtime.

## CI Summary

1. Install the repository-required uv version.
2. Sync `.venv` from `uv.lock` with all extras.
3. Validate changelog fragments (and PR change coverage when `CHANGELOG_BASE_REF` is set).
4. Run `ruff`.
5. Run `pyright`.
6. Run `mypy`.
7. Run unit + contract tests.
8. Run integration tests.

## Policy Boundaries

- Validation and merge-gating policy is owned by `../CI_POLICY.md`.
- Branch, worktree, and PR execution policy is owned by `workflow.md`.

## Update Checklist

- Command or recipe changed -> update this file and the runner in the same change.
- CI workflow changed -> update `just ci` and this file in the same change.
- New required environment variable or config file -> add it here.
- New packaging or distribution path -> document the command and artifact here.
