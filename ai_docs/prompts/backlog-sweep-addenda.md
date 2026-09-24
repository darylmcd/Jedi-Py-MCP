# Backlog remediate addenda

<!-- purpose: Repo-specific facts for the global /backlog-remediate workflow (orchestrator, deepeners, executors, reviewers). Field shapes: ~/.claude/templates/backlog-sweep/addenda.md. -->

## ci_equivalent

```
ci_equivalent: just ci
```

- `just ci` = changelog-check + ruff + converter format check + pyright + mypy + unit/contract tests + integration tests (`scripts/test-integration.ps1`, `RUN_MCP_INTEGRATION=1`). Mirrors `.github/workflows/ci.yml`.
- `changelog-check` compares against `CHANGELOG_BASE_REF`; in a worktree set `CHANGELOG_BASE_REF=<baseRef>` so it validates the branch's own fragments.

## parallel_safety

```
parallel_safety:
  parallelSafe: true
  serializeFullCi: true
  reason: unit/contract tests are hermetic (tmp_path fixtures); the full aggregate spawns Pyright subprocesses for integration tests and is CPU-heavy — serialize full runs.
```

## per_edit_compile / per_edit_test

```
per_edit_compile: .venv/Scripts/python.exe -m pyright <changed files>
per_edit_test: .venv/Scripts/python.exe -m pytest <changed test files> -q
```

## preferred_read_side_tools

- `python-refactor` / `python-analysis` MCP (`find_references`, `search_symbols`, `get_symbol_outline`) for Python symbol reads; `rg` otherwise.

## hotspot_files

- `src/python_refactor_mcp/backends/pyright_lsp.py`
- `src/python_refactor_mcp/backends/rope_backend.py`
- `src/python_refactor_mcp/server.py`
- `src/python_refactor_mcp/tool_registry.py`
- `src/python_refactor_mcp/tool_runtime.py`

## changelogConvention

```
changelogConvention: fragment
```

- Fragment path: `changelog.d/<category>-<row-id>.md` (e.g. `changelog.d/fixed-bl-0004.md`); `scripts/changelog_fragments.py` enforces the `^(fixed|changed-breaking|changed|added|maintenance)-<kebab>.md$` name.
- Body: one bullet `- **Fixed:** <sentence>.` (prefix matches the category heading).

## changelogHeadings

```
changelogHeadings: Fixed | Changed — BREAKING | Changed | Added | Maintenance
```

## worktreeSetup

```
worktreeSetup:
  python:
    dependencyGraft: none
    setup: "uv sync --locked --all-extras   # run with the worktree as cwd; creates the worktree's own .venv with an editable install of ITS src"
    validate: "just ci (CHANGELOG_BASE_REF=<baseRef>)"
    note: "Never reuse the primary checkout's .venv — its editable install points at the primary src."
```

## Contract posture

- Repo is PUBLIC on GitHub; contract-care status is an open operator decision (`~/.claude/CLAUDE.md` Directive #4). 2026-09-24 operator ruling: breaking fixes MAY ship (no ADR/migration note required). A change that removes/renames a tool, a parameter, or rejects previously accepted input MUST still be called out in the PR body and use a `changed-breaking-*` fragment.
