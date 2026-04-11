# Workflow
<!-- purpose: Session workflow, branching, PR handling, backlog closure rules. -->

Scope: session workflow, task scoping, branching, worktrees, PR handling, and delivery rhythm.

## Session Phases

1. Intake: confirm branch, scope, and requested outcome.
2. Context: read required docs and inspect affected files.
3. Execution: make minimal change set needed for correctness.
4. Validation: run required checks from `CI_POLICY.md`.
5. Handoff: summarize changes, validations, risks, and follow-ups.

## Repo Checkpoints

1. Stage awareness: current implementation is Stage 6 complete.
2. Runtime change: update tests in `tests/unit/` in same change.
3. Command change: update `ai_docs/runtime.md`.
4. Process/policy change: update `ai_docs/workflow.md` or `CI_POLICY.md`.
5. Deferred work: add item to `ai_docs/backlog.md` with verification criteria.

## Branch Strategy

- Do not commit directly to the protected default branch.
- Use a task branch for production code changes and for any non-trivial repo change that should be reviewed independently.
- Small local documentation edits may still be prepared without committing, but any merge-ready change should land from a reviewable branch.

## Concurrent Edit Isolation

- If another write-capable session is active or likely, use a dedicated git worktree before editing.
- Use one worktree per parallel writing effort so file changes and branch state stay isolated.
- If worktree creation is not practical, avoid overlapping write scopes and call out the risk.

## Base Branch Sync And Handoff

- Before merge-ready handoff, sync with the base branch when practical or when branch protection requires it.
- Re-run required validation after resolving base-branch drift.
- Respect required reviews, required checks, and any branch protection enforced by the hosting platform.

## Pull Request Handling

- Prefer a normal PR flow from the task branch into the base branch.
- Do not assume GitHub CLI or other hosted PR tooling is installed.
- If PR tooling is unavailable, provide a manual compare URL pattern using the repository host's standard compare route.
- For GitHub-hosted repositories, the fallback pattern is `https://github.com/<owner>/<repo>/compare/<base>...<head>?expand=1`.
- Keep the PR scope aligned with one task or one logical change set.

## Merge-Ready Handoff

- Before handoff, confirm the branch is synchronized with base branch requirements when protection rules require it.
- Re-run required checks after resolving base-branch drift.
- Do not claim merge-readiness when required checks, required reviews, or branch protection conditions remain unmet.

## Backlog Closure

- When work closes backlog rows, update `ai_docs/backlog.md` in the **same PR** or an **immediate** follow-up commit.
- Implementation plans must include a final step: `backlog: sync ai_docs/backlog.md`.
- Do not leave resolved items in the backlog — remove the row, not mark it "done".

## Branch Cleanup

- After merge, clean up merged task branches unless repository policy or an active follow-up requires keeping them.
- Do not reuse stale task branches for unrelated follow-up work.

## Delivery Rhythm

- Share concise progress updates during longer sessions.
- Keep active notes and temporary plans out of `ai_docs`; use scratch space outside the active docs tree.
- Put open follow-up work in `ai_docs/backlog.md` only after verifying it is not complete.