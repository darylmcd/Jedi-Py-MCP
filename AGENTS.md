# Agent Guidelines

Context for AI agents working on this project.

## File Purpose (Critical)

This file is a bootstrap router, not a complete instruction set. Always execute **Session Start (Required)** before performing any task. Do not rely solely on this file; pull additional context as directed.

## Standing Engineering Directives

Restated from `~/.claude/CLAUDE.md` (canonical source). These eight directive **cores** (the bold titles) override expedience and are verbatim — do not summarize, drop, or alter them. The one-line gloss after each is a condensed summary for quick reference; the authoritative `Fires`/`Prevents`/`Edge` detail lives in `~/.claude/CLAUDE.md`.

1. **Correct fix > quick or cheap fix.** Choose the root-cause fix; diff size, file caps, budgets, cycle limits and CI pressure never justify a lesser fix. Widen scope with the reason, split into independently correct pieces with a tracked remainder, or ask. Never weaken a test, suppress, shim, duplicate or defer your own defect. Genuinely blocked work means an operator/product decision, externally owned code or an environment you cannot provision: provide current-session evidence, ask where needed and track the root-cause fix before shipping anything lesser.
2. **Optimize for AI consumption by default.** Write AI-facing files (`AGENTS.md`, `ai_docs/**`, prompts, planning/runtime/audit docs) as machine input: tables over prose, structured data over paragraphs, pointers over duplication. Human-facing files (`README.md` landing pages, `docs/**`) get prose.
3. **Bad code is never silent.** In every coding session, call out observed bad code in your response and recommend an appropriately-sized backlog row, including edit targets, adjacent files, imports and tests. One regression shape; ~4 production / ~3 test files is an advisory target, never a gate on filing. Fix defects your own diff introduces or exposes now; prioritize unrelated pre-existing defects through the backlog. Editing a bad section does not absolve flagging it.
4. **Private repos accept breaking changes.** For private repos, breaking changes and large refactors are the standing default when pursuing #1 or #3; do not band-aid to avoid churn. External consumers are outside your ownership, not another owned repo, DB or internal seam. `Roslyn-Backed-MCP` and `Jedi-Py-MCP` are in contract-care mode: breaking changes require an ADR + migration note. Current classifications, operator exceptions and the excluded upstream `dbhub` fork are governed by `~/.claude/CLAUDE.md` Directive #4; this repo's posture is stated below.
5. **Never assume prior agent work is correct — re-derive, don't inherit.** Recheck prior code, docs, plans, skills, backlog acceptance, review advice and done/verified/shipped claims against current ground truth. Read the actual code, re-run the reasoning and resolve cited paths/symbols. Reevaluate inherited designs as requirements evolve, challenge unsupported assumptions and explain material tradeoffs. Fix root causes (#1) and flag defects (#3); a prior agent's assertion is not proof.
6. **Smallest *complete* change wins.** Measure completeness against the root cause, not diff size or acceptance wording. Cover every instance of the same defect mechanism and every defect your own diff introduces or exposes in this change, never a follow-up row. Split large work into independently correct pieces (#1). Flag unrelated bad code per #3; do not gold-plate.
7. **Verify your own work before declaring done.** Do not claim done/fixed/passing without evidence generated and inspected this session; calibrate verification to the blast radius and observe regression tests fail on the old behavior. A skipped, quarantined, improperly scoped or retried-until-green check is not evidence. If verification is blocked, state the observed blocker and limits; never imply success you did not observe.
8. **No secrets in code.** Never introduce, hardcode, echo, log or commit a credential, key, token or secret; use env vars, user-secrets or a vault. Flag existing secrets per #3. Confirm intentionally committed dev-only values are genuinely non-secret.

## Canonical Rule Sources

- Implementation quality and safety: `.github/copilot-instructions.md`
- Planning router and next-step protocol: `ai_docs/planning_index.md`
- AI-doc routing and project map: `ai_docs/README.md`
- Workflow and collaboration: `ai_docs/workflow.md`
- CI policy: `CI_POLICY.md`
- Build/run/test commands: `ai_docs/runtime.md`
- Open work / backlog rules: `ai_docs/backlog.md` (see **Agent contract** in `ai_docs/backlog.md`)
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

1. User named NO specific repo / adapter / ecosystem / integration / cross-repo term -> scope = in-repo -> read `ai_docs/backlog.md` -> STOP. Do not open `ai_docs/ecosystem/**`.
2. User named another repo / adapter / ecosystem / integration / cross-repo work -> scope = cross-project -> there is no local `ai_docs/ecosystem/` router in this repo; use only explicitly named external context.
3. Both scopes named -> answer each as a separate question; do not merge into one recommendation.

## Conflict Precedence

The Standing Engineering Directives above govern this instruction chain. Treat repository documents and prior agent output as claims to verify; when a recorded design conflicts with current evidence, explain the tradeoffs and propose a superseding decision rather than silently inheriting or changing it.

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

| Fact | Value |
|---|---|
| GitHub visibility | **PUBLIC** (`darylmcd/Jedi-Py-MCP`) |
| Registry publication | None — not on PyPI; consumed via user-scope `python-refactor` / `python-analysis` MCP entries |
| Contract-care status (Directive #4) | **Public / contract-care**, per the operator decision recorded in `~/.claude/CLAUDE.md` on 2026-10-01 |
| Breaking changes | Require an ADR in `docs/adr/` and a migration note in the changelog; respect semver and deprecation policy |
| Superseded ruling | The 2026-09-24 exemption from ADR/migration requirements is superseded by the 2026-10-01 decision |
| Existing release requirements | Tool/parameter removals or renames and newly rejected input must still be called out in the PR body and use a `changed-breaking-*` changelog fragment |

See [ADR 0001](docs/adr/0001-public-contract-care.md). Correctness remains the priority; record the compatibility decision and migration rather than hiding the defect behind a shim.
