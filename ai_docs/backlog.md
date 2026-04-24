# Backlog
<!-- purpose: Open follow-up work items only — remove entries when completed. -->
<!-- scope: in-repo -->

**updated_at:** 2026-04-24T00:00:00Z

## Agent contract

- This file contains **unfinished work only**. Remove or update rows when work ships.
- MUST NOT add completed-history sections or use the backlog as a changelog — `CHANGELOG.md` is the human-facing history, git history is the canonical record, and this backlog holds only open work.
- Implementation plans MUST include a final step: `backlog: sync ai_docs/backlog.md`.
- Release-affecting changes MUST add a bullet under `## [Unreleased]` in `CHANGELOG.md` in the same PR that ships the change.
- Each row has a stable `id` for grep-friendly referencing.

## Standing rules

- Best practices reference: `ai_docs/references/mcp_best_practices.md`.
- Historical plans, audits, and reports removed — originals preserved in git history.
- Priority tiers: Critical > High > Medium > Low > Defer.

## Open items

| id | priority | area | item | blocker |
|----|----------|------|------|---------|
| known-rope-annotations | Low | upstream | `change_signature` strips Python 3 type annotations during normalization (rope `ArgumentNormalizer`). Documented in `backends/rope_backend.py`. | rope upstream |
| mcp-checklist-prompts | Low | docs | Complete prompt example bank for all tools in `ai_docs/domains/python-refactor/mcp-checklist.md`. | none |

## Refs

- `ai_docs/workflow.md` — execution flow and backlog closure rules
- `ai_docs/references/mcp_best_practices.md` — MCP design reference
