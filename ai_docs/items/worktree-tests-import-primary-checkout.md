# worktree-tests-import-primary-checkout — Tests run in a worktree exercise the primary checkout's code

**row:** `worktree-tests-import-primary-checkout` · **pri:** `Medium` · **size:** `M`

## Anchors

- `tests/conftest.py`
- `tests/integration/conftest.py:42`

## Acceptance

- [ ] A test run from a worktree imports that worktree's python_refactor_mcp, or aborts with a message naming both paths.
- [ ] A regression test or session-start assertion shows python_refactor_mcp.__file__ is under the repo root being tested.

## Evidence

- 2026-11-18 remediate: every lane worker reported setting PYTHONPATH=<worktree>/src because the venv editable install pointed at D:/Jedi-Py-MCP/src; without it a worktree's tests pass or fail against main's code.
