# integration-tests-skip-silently-without-venv — Integration tests skip silently when .venv is absent

**row:** `integration-tests-skip-silently-without-venv` · **pri:** `Low` · **size:** `S`

## Anchors

- `tests/integration/conftest.py:42`
- `scripts/test-integration.ps1:8`

## Acceptance

- [ ] With RUN_MCP_INTEGRATION=1 and no .venv beside the repo root the suite uses sys.executable (or errors), never skips.
- [ ] test-integration.ps1 in a worktree runs the integration suite or exits non-zero with a reason.

## Evidence

- 2026-11-18 remediate: workers needed a temporary .venv junction in each worktree to run the integration tests; without it the tests skipped (conftest.py:42-45) and test-integration.ps1 failed on xdist.
