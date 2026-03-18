# Agent Bootstrap

Purpose: minimal canonical bootstrap path for AI sessions.

## Required Read Order

1. `.github/copilot-instructions.md`
2. `CLAUDE.md`
3. `ai_docs/README.md`
4. `ai_docs/runtime.md`
5. `ai_docs/workflow.md`
6. `CI_POLICY.md`
7. `ai_docs/backlog.md`
8. `.cursor/rules/operational-essentials.md`

## Precedence

1. Direct user request
2. Canonical repository docs listed in this file
3. Archived or non-canonical notes

## Canonical Owners

- Implementation behavior, safety, and definition of done: `.github/copilot-instructions.md`
- Claude-specific bootstrap alignment: `CLAUDE.md`
- AI doc routing and project map: `ai_docs/README.md`
- Environment and command facts: `ai_docs/runtime.md`
- Execution flow, branching, and PR workflow: `ai_docs/workflow.md`
- Validation and merge-gate policy: `CI_POLICY.md`
- Open follow-up work only: `ai_docs/backlog.md`
- Reminder-only operational checklist: `.cursor/rules/operational-essentials.md`

## Fast Session Start

1. Confirm active branch and workspace root.
2. Read the required docs above in order.
3. Verify command surface from `ai_docs/runtime.md`.
4. Execute using `ai_docs/workflow.md` and validate per `CI_POLICY.md`.

## Standard Validation Commands

- `python -m ruff check .`
- `python -m pyright .`
- `python -m mypy .`
- `python -m pytest tests/unit/ -v`
- `./scripts/build.ps1`

Keep this file short and route detail updates to owning docs.