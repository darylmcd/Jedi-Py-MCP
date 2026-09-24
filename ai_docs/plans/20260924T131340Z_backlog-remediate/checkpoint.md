# Checkpoint — 20260924T131340Z_backlog-remediate

Written 2026-09-24. Stop reason: account weekly usage limit hit mid-generation-1 (subagents fail until **2026-09-28 09:00 America/Chicago**). Every PR requires a cold `implementation-reviewer` subagent, so no further initiative can land before the reset.

## Landed

| id | PR | merge commit | gate |
|---|---|---|---|
| bl-0001 | #110 | df43af8 | integration-gate exit 0; landed tree == gated tree 986f4bc |
| bl-0002 | #112 | fe9f8c4 | exit 0; tree 08790af |
| bl-0004 | #113 | 94abebe | exit 0; tree 40b6e80 |
| bl-0008 | #114 | 1b59496 | exit 0; tree e749fc1 |
| (hotfix) | #115 | 0fa7b01 | unbroke main: #109 (plan PR) merged with non-required `Validate` red (tool count in `ai_docs/items/bl-0020.md`) |

## Gated but unlanded

| id | branch | PR | state |
|---|---|---|---|
| bl-0006 | remediation/bl-0006 | #111 | review verdict fail (module/package `apply=True` created no file). Fixed inline by orchestrator in 6850ad2 (+ real-rope apply test); local pytest/pyright/ruff/mypy green. NEEDS: cold re-review (cycle 2), then integration gate + land. Not gated yet. |

## Next actions

1. After the reset: `/backlog-remediate plan-id=20260924T131340Z_backlog-remediate`.
2. bl-0006: dispatch `implementation-reviewer` (mode serial, implementation inline for the fix commit, baseRef 5f9f1874670f7123d301ab4f8316cc7b44b07b02, worktree `.worktrees/bl-0006`); on pass → integration-gate (`--ci-cmd 'uv sync --locked --all-extras -q && CHANGELOG_BASE_REF=origin/main just ci'`) → land.
3. bl-0011, bl-0015: infra-death (usage limit), no work produced; worktrees torn down, status `pending`. Re-run in the next generation-1 recompute.
4. Remaining pending: bl-0005, bl-0007, bl-0010, bl-0012, bl-0013, bl-0014, bl-0016 (generations 2–6; dependencies on bl-0002 now satisfied).
5. Integration gates need the custom `--ci-cmd` above (integration worktree has no `.venv`).

## Deviations

- Plan PR #109 merged with the (non-required) `Validate` check red — `watch-pr` reports advisory failures as READY. Fixed by #115. From now on, confirm `Validate` = pass via `gh pr checks` before any merge.
- Gen-1 PR branches #110/#112/#113/#114 showed red CI inherited from the #109 break; each was proven green by its integration gate on current main before landing.
- bl-0006 fix was implemented inline by the orchestrator (review-fail fix loop) because fix subagents were unavailable; it still requires a cold review.
- `ai_docs/items/bl-0020.md` Context line hand-edited in #115 (`backlog.mjs update` has no Context section).
- `.worktrees/` added to the primary's `.git/info/exclude` (not `.gitignore`).

## Spin-off sketches

- Make `Validate (Python 3.14, Windows)` a required status check on `main` (branch protection) so non-green PRs cannot read as READY.
- Add `.worktrees/` to `.gitignore`.
- `apply_code_action` description (`tool_registry.py:605`) says omitting `action_title` lists actions; `_pick_code_action` applies `actions[0]`.
- Convert remaining caller-input `ValueError` sites (structural.py, hierarchy.py, rename.py, outline.py, diagnostics.py, type_users.py, search/_helpers.py, server.py:239) to `ToolInputError` (overlaps open bl-0003 — amend it rather than file new).
- `tools/refactoring/imports.py:71,78` raise `ValueError` for bad rope output → `RopeError`.
- Silent `[]` on unhandled LSP methods at `pyright_lsp.py:754,964,980,996,1118,1138,1368,1405,1428`.
- `PATH_PARAMS` (`tool_runtime.py:32-39`) lacks `*_dir` params → folder args skip workspace-boundary checks.
- `SignatureOperation.new_order` accepts negatives silently.
- `prepare_rename` `{defaultBehavior}` + placeholder paths index by code point, LSP uses UTF-16.
- `AGENTS.md` says the repo is private; it is PUBLIC.
- Global tooling (`~/.claude`): `watch-pr` READY on non-required red checks; `backlog.mjs update` lacks a Context section; execute.js legacy "read FULL stanza" vs agents' 5120-byte bound.
