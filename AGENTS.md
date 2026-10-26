# Agent Guidelines

Context for AI agents working on this project.

## File Purpose (Critical)

This file is a bootstrap router, not a complete instruction set. Always execute **Session Start (Required)** before performing any task. Do not rely solely on this file; pull additional context as directed.

## Standing Engineering Directives

Restated from `~/.claude/CLAUDE.md` (canonical source). These eight numbered lines are copied verbatim from that file's directive block — do not summarize, drop, or alter them; the sub-clauses (forbidden moves, routing, change-set rule, not-evidence list) live only there and outrank anything below.

1. **Correct fix > quick or cheap fix.** When a quick or cheap fix and a correct fix are both viable, ship the correct one — root cause, not symptom. Cost never decides: diff size, any budget (files, tokens, turns, wall-clock), CI or landing pressure, and model tier are never reasons for the lesser fix. No plan, brief, row, rubric or reviewer severity can authorize a lesser fix; only the operator can, one item and PR head at a time, and "ship it" or "get it green" authorize the correct fix, not a lesser one.
2. **Optimize for AI consumption by default.** Nearly every document in these repos is AI-facing (`AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, `.github/prompts/**`, `ai_docs/**`, planning/runtime/audit docs): write them as machine input — tables over prose, structured data over paragraphs, pointers over duplication, short imperative sentences over narrative. Human-facing files (`README.md` landing pages, `docs/**`) get human prose. The density rules are doc-audit `STANDARD.md` §Quality Rules.
3. **Bad code is never silent.** When you observe bad code — in the file you were sent to edit, an adjacent file opened for context, an import target, a test, anything you read solving the task — call it out in your response and recommend a backlog row sized per doc-audit `STANDARD.md`. Editing a bad section does not absolve flagging it.
4. **Private repos accept breaking changes.** For private repos, breaking changes and large refactors are the standing default when pursuing #1 or #3 — rip it out, don't band-aid to avoid churn, even at the cost of a temporarily non-functional app. An external consumer is a published package/marketplace artifact or a third party, never another owned repo, a database the repo owns, or an internal seam (you own both ends; break one and you own the ticket). Which repos are public or in contract-care (ADR + migration note) is the **Repo posture** table in `~/.claude/CLAUDE.md`; only publication, or an operator decision recorded there, flips a repo.
5. **Never assume prior agent work is correct — re-derive, don't inherit.** Work product from any previous session — code, docs, skills, prompts, backlog rows, plans, audit findings, anything labeled done/verified/shipped — is a claim to check against current ground truth: read the actual code, re-run the reasoning, confirm cited paths/symbols/versions still resolve. Never take a commit message, comment, or doc's say-so as proof.
6. **Smallest *complete* change wins.** Correct ≠ maximal: #1 and #4 license root-cause fixes and breaking changes; they do not mandate gold-plating. Complete = the root cause + every instance of the same defect mechanism (same function, shared helper, or copy — found by probing the construct with references/grep and listed with `file:line`) + every defect your own diff introduces or exposes (duplication, weak or missing test, untested new branch, stale comment, suppression, shim, a new test that fails on a real bug). Measure against the root cause — not diff size, and not acceptance text that may encode the symptom.
7. **Verify your own work before declaring done.** Don't claim done/fixed/passing without evidence you generated THIS session — ran the test, read the output, exercised the path; "it should work" is not verification. Calibrate depth to blast radius. Can't verify (no runner, can't drive the UI)? Say so explicitly — never imply success you didn't observe.
8. **No secrets in code.** NEVER introduce, hardcode, echo, log, or commit a credential, key, token, or secret — they live in env vars / user-secrets / a vault, not source. Intentionally committed dev-only non-secrets (e.g. TradeWise's compose creds) are fine once you confirm they are truly non-secret. An EXISTING hardcoded secret is flagged per #3; this rule forbids *introducing* one.

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
- Do not introduce features or scope outside documented backlog and constraints, except the scope Standing Directives #1 and #6 require (same-mechanism instances, defects your own diff introduces or exposes).

## Breaking-change posture

This is a **public repo** (per `.ai-doc-audit.md` `repo_class: public`). Breaking changes require an ADR in `docs/adr/` plus a migration note in the changelog; external consumers depend on this surface — respect semver and deprecation cycles. Facts:

| Fact | Value |
|---|---|
| GitHub visibility | **PUBLIC** (`darylmcd/Jedi-Py-MCP`) |
| Registry publication | None — not on PyPI; consumed via user-scope `python-refactor` / `python-analysis` MCP entries |
| Contract-care status (Directive #4) | **Public / contract-care**, per the operator decision recorded in `~/.claude/CLAUDE.md` on 2026-10-01 |
| Breaking changes | Require an ADR in `docs/adr/` and a migration note in the changelog; respect semver and deprecation policy |
| Superseded ruling | The 2026-09-24 exemption from ADR/migration requirements is superseded by the 2026-10-01 decision |
| Existing release requirements | Tool/parameter removals or renames and newly rejected input must still be called out in the PR body and use a `changed-breaking-*` changelog fragment |

See [ADR 0001](docs/adr/0001-public-contract-care.md). Correctness remains the priority; record the compatibility decision and migration rather than hiding the defect behind a shim.

## Machine-wide validation

- On the shared Windows dev host, run `just machine-validate` for the full gate or `just machine-validate <recipe>` for a named build/test recipe.
- The shared helper is `~/.claude/scripts/validation-gate.mjs`; its machine-wide capacity covers every participating repo and worktree. Wait for admission; never launch an unwrapped equivalent while waiting.
- For a raw validation command, call `node <absolute-user-profile>/.claude/scripts/validation-gate.mjs -- <executable> [arguments...]`. Pass an interpreter explicitly for shell scripts.
- Preserve the existing gate, test selection, exit status and desktop ownership requirements. The wrapper adds admission only; `just ci` remains the underlying full gate.
- Full contract: `~/.claude/ai_docs/validation-gate.md`. This local helper is required only for the shared dev-host entry; other contributors and hosted CI may use the underlying commands directly.
