# Agent Guidelines

Context for AI agents working on this project.

## File Purpose (Critical)

This file is a bootstrap router, not a complete instruction set. Always execute **Session Start (Required)** before performing any task. Do not rely solely on this file; pull additional context as directed.

## Standing Engineering Directives

Restated from `~/.claude/CLAUDE.md` (canonical source). These eight directive **cores** (the bold titles) override expedience and are verbatim — do not summarize, drop, or alter them. The one-line gloss after each is a condensed summary for quick reference; the authoritative `Fires`/`Prevents`/`Edge` detail lives in `~/.claude/CLAUDE.md`.

1. **Correct fix > quick fix.** Choose the root-cause fix over the symptom patch. A quick fix is acceptable only when the correct fix is genuinely out of scope — then say why and file a backlog row (per #3) before shipping it.
2. **Optimize for AI consumption by default.** Write AI-facing files (`AGENTS.md`, `ai_docs/**`, prompts, planning/runtime/audit docs) as machine input: tables over prose, structured data over paragraphs, pointers over duplication. Human-facing files (`README.md` landing pages, `docs/**`) get prose.
3. **Bad code is never silent.** When you observe bad code in ANY file you touch (the edit target, an adjacent file, an import, a test), (a) call it out and (b) recommend an appropriately-sized backlog row (≤4 prod files, ≤3 test files, one regression shape). Editing a bad section does not absolve the obligation to flag it.
4. **Private repos accept breaking changes.** For private repos (everything under `C:/Code-Repo/` EXCEPT `Roslyn-Backed-MCP`), breaking changes are the standing default when pursuing #1 or #3 — rip it out. "External consumer" = outside your ownership (a published artifact or third party); another local repo, an owned DB, or internal cross-repo coupling do NOT count. Only publication flips a repo into ADR + migration mode.
5. **Never assume prior agent work is correct — re-derive, don't inherit.** Work labeled done/verified/shipped carries no presumption of correctness; check it against current ground truth (read the code, re-run the reasoning, confirm cited paths still resolve). Fires with special force on model-handoff reviews.
6. **Match change size to task value.** Correct ≠ maximal. #1 and #4 license root-cause fixes and breaking changes but do not mandate gold-plating — the smallest change that fully fixes the root cause wins. Flag adjacent bad code per #3 rather than fixing it inline.
7. **Verify your own work before declaring done.** Don't claim done/fixed/passing without evidence you generated this session (ran the test, read the output, exercised the path). Can't verify? Say so — don't imply success you didn't observe.
8. **No secrets in code.** Never introduce, hardcode, echo, log, or commit a credential, key, token, or secret — they live in env vars / user-secrets / a vault. Finding an existing one = flag per #3.

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

## Default Behavior (When Ambiguous or Incomplete)

- Prefer repository-specific conventions over generic defaults.
- Prefer safety, validation, and correctness over speed.
- Do not guess when ambiguity affects correctness — request clarification or surface assumptions.
- Do not introduce features or scope outside documented backlog and constraints.

## Breaking-change posture

This is a **private repo** (per `.ai-doc-audit.md` `repo_class: private`). Breaking changes and large refactors are ALWAYS acceptable when pursuing Standing Directive #1 (correct fix) or #3 (bad code remediation). There are no external consumers to break. Do not band-aid problems to avoid churn — rip them out.
