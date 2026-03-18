# Copilot Instructions

Scope: behavior and quality guardrails for AI contributors.

Session bootstrap:

- Start with `AGENTS.md` for canonical read order.
- Use `ai_docs/README.md` as the AI-doc routing index.

Implementation guardrails:

- Prefer minimal, correct changes over broad speculative refactors.
- Fix root causes when the scope is clear; do not paper over issues with doc-only claims or temporary hacks.
- Preserve unrelated user changes and avoid reverting work you did not make.
- Keep active documentation current-state only; archive historical rationale instead of mixing it into bootstrap docs.
- Do not invent commands, tools, services, or automation that are not verified in this repository.
- When commands or tooling are absent, state that explicitly and keep guidance generic.
- Prefer one canonical location per policy area; link to workflow, runtime, or CI docs instead of restating them.

Validation expectations:

- Validation and merge-gating policy is owned by `CI_POLICY.md`.
- Runtime command facts are owned by `ai_docs/runtime.md`.
- Branch/worktree/PR process is owned by `ai_docs/workflow.md`.

Definition of done:

- The requested change is implemented or the blocker is explicit.
- Changed files are internally consistent and do not contradict `ai_docs/workflow.md`, `ai_docs/runtime.md`, or `CI_POLICY.md`.
- References and paths added by the change are valid.
- Any remaining risks, skipped checks, or follow-up work are called out in the final handoff.

For workflow rules, see `ai_docs/workflow.md`. For environment and tooling assumptions, see `ai_docs/runtime.md`. For merge and validation policy, see `CI_POLICY.md`.