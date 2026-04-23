# Planning Index
<!-- purpose: Routing index for planning docs and next-step answers. -->
<!-- scope: in-repo -->

## Agent contract

- Default scope: unnamed scope = in-repo; do NOT open `ecosystem/` unless the user explicitly named cross-repo or integration work.
- In-repo read order: `backlog.md`.
- Cross-project read order: this repo has no local `ai_docs/ecosystem/` planning docs; use only explicitly named external repo or integration context.
- MUST: every planning file carries a scope tag.
- MUST: cross-project and reference files carry the required scope banner.
- MUST NOT: duplicate roadmap content here; this file is a router only.
- MUST NOT: mix scopes within a routing-table section.

## Next-step protocol

1. User named NO specific repo / adapter / ecosystem / integration / cross-repo term -> scope = in-repo -> read `backlog.md` -> STOP. Do not open `ai_docs/ecosystem/**`.
2. User named another repo / adapter / ecosystem / integration / cross-repo work -> scope = cross-project -> there is no local `ai_docs/ecosystem/` router in this repo; use only explicitly named external context.
3. Both scopes named -> answer each as a separate question; do not merge into one recommendation.

## Routing

| Scope | If you are answering... | Open first | Then |
|-------|--------------------------|------------|------|
| in-repo | "What is the next step here?" or local follow-up work in this repo | `backlog.md` | `workflow.md` and `architecture.md` as needed |
| cross-project | Another repo, adapter, ecosystem, integration, or cross-repo scope | none | Use only explicitly named external context |
| reference | Commands, architecture, testing, tool surface, or procedures | `runtime.md`, `architecture.md`, `references/testing.md` | `domains/python-refactor/reference.md`, `procedures/release-handoff.md`, `prompts/deep-review-refactor.md` |

## Maintenance

- Keep this file routing-only; do not duplicate backlog rows or workflow policy here.
- Update this file and `AGENTS.md` together when the next-step protocol changes.
- When a new in-repo planning file is added, give it a scope tag and register it here.
- Keep cross-project files out of `ai_docs/README.md` unless they live under an `Ecosystem` section.
