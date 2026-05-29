# Agent Guidelines

Context for AI agents working on this project.

## File Purpose (Critical)

This file is a bootstrap router, not a complete instruction set. Always execute **Session Start (Required)** before performing any task. Do not rely solely on this file; pull additional context as directed.

## Standing Engineering Directives

Restated from `~/.claude/CLAUDE.md`. These five rules override expedience. Do not summarize, drop, or alter.

1. **Correct fix > quick fix.** When a quick fix and a correct fix are both viable, choose the correct fix. The correct fix addresses the root cause; the quick fix patches a symptom. Quick fixes are only acceptable when the correct fix is genuinely out of scope for the current task — and when that happens, file a backlog row (per rule #3) for the correct fix before shipping the quick one. "We'll fix it later" without a tracked row = does not exist.

2. **Optimize for AI consumption by default.** 99% of files in this repo are AI-facing: `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, `.github/prompts/**`, `ai_docs/**`, planning docs, runtime references, audit reports. Optimize them for fast, dense parsing: tables over prose, structured data over paragraphs, pointers over duplication, short imperative sentences over narrative. Human-facing files (`README.md` at landing-page level, `docs/**`) get human prose. Everywhere else, AI-optimized.

3. **Bad code is never silent — this rule fires in EVERY coding session.** Not just doc-audit. Not just code review. Every session where you read, edit, fix, refactor, debug, navigate, or otherwise touch code. When you observe bad code — dead code paths, swallowed exceptions, hardcoded values that should be config, hardcoded credentials/secrets, commented-out blocks, TODO/FIXME/HACK/XXX markers without a tracking row, obvious anti-patterns, security smells, broken naming, suspiciously stale comments, copy-paste duplication, god classes, layering violations, sync-over-async, untested critical paths — you MUST (a) call it out in your response to me and (b) recommend an appropriately-sized backlog row (≤4 production files, ≤3 test files, one regression shape per doc-audit STANDARD). **Applies whether the bad code is the file you were sent to edit, an adjacent file you opened for context, an import target, a test file, or anything you read in the course of solving the task.** Critically: if you are FIXING a code section and it is bad/poorly-written/incorrect, surfacing it is mandatory even if the fix is "in scope" — the act of editing does not absolve the obligation to flag. The right *time* to fix the bad code is when the row's priority demands it, not when you happen to be in the file — but **the row MUST exist**. Silently editing around bad code, polishing a bad pattern without flagging, or "I'll mention it if asked" all count as misses.

4. **Private repos accept breaking changes.** For private repos (everything under `C:/Code-Repo/` EXCEPT `Roslyn-Backed-MCP`), breaking changes and large refactors are ALWAYS acceptable when pursuing rule #1 or #3. Don't band-aid a private-repo problem to avoid churn; rip it out. For `Roslyn-Backed-MCP`, breaking changes require an ADR + migration note.

5. **Never assume prior agent work is correct — re-derive, don't inherit.** Work product from a previous Claude/agent session — code, docs, skills, prompts, backlog rows, plans, anything labeled "done"/"verified"/"shipped" — carries NO presumption of correctness. Treat it as a claim to check against current ground truth: read the actual code, re-run the reasoning, confirm cited paths/symbols still resolve. This fires with special force during model-handoff reviews (a newer model proof-reading an older model's work) and on anything asserted complete. Fix root causes (rule #1) and flag what you find (rule #3) rather than papering over inherited defects.

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

This is a **public repo** (per `.ai-doc-audit.md` `repo_class: public`). Breaking changes require an ADR in `docs/adr/` (or `docs/adrs/` per local convention) plus a migration note in the CHANGELOG. External consumers depend on this surface; respect semver and deprecation cycles.
