# Copilot Instructions

Scope: implementation quality, engineering behavior, safety, and definition of done.

Session bootstrap:

- Start with `AGENTS.md` to locate canonical docs and required read order.
- Use `ai_docs/README.md` as the routing map for project structure and doc ownership.

Implementation guardrails:

- Prefer minimal, correct changes over broad speculative refactors.
- Fix root causes when the scope is clear; do not paper over issues with doc-only claims or temporary hacks.
- Preserve unrelated user changes and avoid reverting work you did not make.
- Keep active documentation current-state only; archive historical rationale instead of mixing it into bootstrap docs.
- Do not invent commands, tools, services, or automation that are not verified in this repository.
- When commands or tooling are absent, state that explicitly and keep guidance generic.
- Prefer one canonical location per policy area; link to workflow, runtime, or CI docs instead of restating them.

Validation expectations:

- Validate the files you changed using the commands or checks defined in `CI_POLICY.md` when those checks exist.
- If no automated checks exist for the change, perform a consistency review of the affected docs or code paths and say what was not validated.
- Treat warnings, failing diagnostics, and broken links introduced by your change as work to resolve before handoff.

Definition of done:

- The requested change is implemented or the blocker is explicit.
- Changed files are internally consistent and do not contradict `ai_docs/workflow.md`, `ai_docs/runtime.md`, or `CI_POLICY.md`.
- References and paths added by the change are valid.
- Any remaining risks, skipped checks, or follow-up work are called out in the final handoff.

For workflow rules, see `ai_docs/workflow.md`. For environment and tooling assumptions, see `ai_docs/runtime.md`. For merge and validation policy, see `CI_POLICY.md`.