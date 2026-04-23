# Testing Reference
<!-- purpose: Stable reference for validation commands and test execution. -->

Purpose: stable reference for local validation and test execution.

## Canonical Policy

- Validation and merge-gating policy is owned by `../../CI_POLICY.md`.
- The primary local entrypoint is `just ci`; use direct commands below when you need a single lane.

## Standard Commands

| Purpose | Direct command | Runner |
|---|---|---|
| Unit tests | `python -m pytest tests/unit/ -v` | `just test` |
| Integration tests | `./scripts/test-integration.ps1` | `just test-integration` |
| Lint | `python -m ruff check .` | `just lint` |
| Type check (Pyright) | `python -m pyright .` | `just typecheck` |
| Type check (mypy) | `python -m mypy .` | `just typecheck-mypy` |
| Full local CI mirror | aggregate: lint + pyright + mypy + unit + integration | `just ci` |

## Notes

- Integration coverage runs through `scripts/test-integration.ps1`, not `pytest tests/integration/`.
- Keep environment assumptions in `../runtime.md`, not here.
