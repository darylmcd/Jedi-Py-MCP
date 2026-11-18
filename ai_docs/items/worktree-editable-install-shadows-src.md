# worktree-editable-install-shadows-src — Make worktree test runs import their own src

**row:** `worktree-editable-install-shadows-src` · **pri:** `Low` · **size:** `S` · **verified:** `b935c2cda00eea0c75a6e613ff7b8f416f543391`

## Anchors

- `pyproject.toml:60`

## Acceptance

- [ ] Running pytest from a git worktree imports that worktree's `src`, not the primary checkout's, with no manual PYTHONPATH (for example `pythonpath = ["src"]` under the pytest ini options), proven by a test that asserts the module file location.
- [ ] Document the local runner expectations in `ai_docs/runtime.md` (xdist `-n` needs pytest-xdist installed in the venv).

## Evidence

- Four lane workers in the 2026-11-17 remediation run found the venv editable install resolves `python_refactor_mcp` to the primary checkout, so worktree pytest runs silently test main's code unless PYTHONPATH is set; that venv also lacked pytest-xdist, so the documented `-n logical` runner failed.
