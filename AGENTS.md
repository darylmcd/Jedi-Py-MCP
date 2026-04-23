# Agent Guidelines

Context for AI agents working on this project.

## Canonical Rule Sources

- Implementation quality and safety: `.github/copilot-instructions.md`
- Planning router and next-step protocol: `ai_docs/planning_index.md`
- AI-doc routing and project map: `ai_docs/README.md`
- Workflow and collaboration: `ai_docs/workflow.md`
- CI policy: `CI_POLICY.md`
- Build/run/test commands: `ai_docs/runtime.md`
- Open work / backlog rules: `ai_docs/backlog.md` (see **Agent contract** in that file)
- Operational reminder layer: `.cursor/rules/operational-essentials.md`
- Claude pointer: `CLAUDE.md` points to this file (collapsed-pointer form — no mirror)

## Session Start (Required)

At the start of every new session, read these files before doing work:

1. `.github/copilot-instructions.md`
2. `ai_docs/workflow.md`
3. `CI_POLICY.md`
4. `ai_docs/runtime.md`
5. `ai_docs/planning_index.md`
6. `.cursor/rules/operational-essentials.md`

After the required reads, use `ai_docs/README.md` to pull additional docs on demand for the current task.

Next-step protocol:

1. User named NO specific repo / adapter / ecosystem / integration / cross-repo term -> scope = in-repo -> read `backlog.md` -> STOP. Do not open `ai_docs/ecosystem/**`.
2. User named another repo / adapter / ecosystem / integration / cross-repo work -> scope = cross-project -> there is no local `ai_docs/ecosystem/` router in this repo; use only explicitly named external context.
3. Both scopes named -> answer each as a separate question; do not merge into one recommendation.

## Conflict Precedence

- For implementation quality and safety conflicts, follow `.github/copilot-instructions.md`.
- For planning and open-work routing conflicts, follow `ai_docs/planning_index.md` and `ai_docs/backlog.md`.
- For workflow and collaboration conflicts, follow `ai_docs/workflow.md`.
- For CI policy conflicts, follow `CI_POLICY.md`.
- For build/run environment details, follow `ai_docs/runtime.md`.
