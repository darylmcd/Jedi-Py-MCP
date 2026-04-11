# Testing Reference
<!-- purpose: Stable reference for validation commands and test execution. -->

Purpose: stable reference for validation and test execution.

## Canonical Policy

- Validation and merge-gating policy is owned by `../../CI_POLICY.md`.

## Standard Commands

- `python -m pytest tests/unit/ -v`
- `python -m pytest tests/integration/ -v`
- `python -m ruff check .`
- `python -m pyright .`
- `python -m mypy .`

## Notes

- Integration tests may require additional local runtime setup.
- Keep environment assumptions in `../runtime.md`, not here.
