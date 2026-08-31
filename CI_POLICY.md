# CI Policy

Scope: validation requirements, merge gates, and handling of failing checks.

## Snapshot

- Local quality commands are defined and runnable.
- Hosted CI is configured in `.github/workflows/ci.yml` and runs changelog
  validation, lint, targeted semantic-converter formatting, type checking,
  unit + contract tests, and integration tests on Python 3.14 (Windows).
- The CI job mirrors the local validation table exactly; update both together
	when commands or tooling change.

## Standard Validation Commands

| Scope | Command |
|---|---|
| Changelog fragments | python scripts/changelog_fragments.py |
| Lint | python -m ruff check . |
| Semantic converter formatting | python -m ruff format --check src/python_refactor_mcp/tools/refactoring/_converter_preflight.py src/python_refactor_mcp/tools/refactoring/dataclass_conversion.py src/python_refactor_mcp/tools/refactoring/typed_dict_conversion.py src/python_refactor_mcp/tools/refactoring/pydantic_conversion.py tests/unit/test_semantic_converters.py |
| Type check (Pyright) | python -m pyright . |
| Type check (mypy) | python -m mypy . |
| Unit + contract tests | python -m pytest tests/unit/ tests/contract/ -v |
| Integration tests | ./scripts/test-integration.ps1 |

## Validation Contract

- For code changes, run applicable commands from the standard validation set and report results.
- Pull-request CI sets `CHANGELOG_BASE_REF` so material changes must include a changed, valid fragment.
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
