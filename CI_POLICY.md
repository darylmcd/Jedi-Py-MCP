# CI Policy

Scope: validation requirements, merge gates, and handling of failing checks.

## Snapshot

- Local quality commands are defined and runnable.
- Hosted CI is not configured yet.

## Standard Validation Commands

| Scope | Command |
|---|---|
| Lint | python -m ruff check . |
| Type check (Pyright) | python -m pyright . |
| Type check (mypy) | python -m mypy . |
| Unit tests | python -m pytest tests/unit/ -v |

## Validation Contract

- For code changes, run applicable commands from the standard validation set and report results.
- For documentation-only changes, perform a consistency review (path validity, policy consistency, stale guidance).
- If a command is intentionally skipped, state why and call out risk.

## Merge Gates

- Respect branch protection, required reviews, and required status checks when the hosting platform enforces them.
- Do not bypass failing required checks without an explicit maintainer decision.
- If a known failure is unrelated to the change, document the failure clearly and note why it is out of scope.

## Failing Checks

- New failures caused by the change block handoff.
- Pre-existing failures may be left unresolved only when they are documented as unrelated and the reviewer can reproduce that assessment.
- Missing automation is not the same as passing validation; call out the gap.

If this repository later adds automated checks, update this file first and keep other docs referring back here instead of duplicating the policy.