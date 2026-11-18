# ruff-format-drift — ruff format flags 81 files repo-wide; CI gates only 5

**row:** `ruff-format-drift` · **pri:** `Low` · **size:** `M` · **verified:** `56acf734d43c24c331918b47ac75a7fbe6956ad4`

## Anchors

- `pyproject.toml:42`
- `justfile:6`
- `justfile:50`
- `src/python_refactor_mcp/__init__.py:3`

## Acceptance

- [ ] ruff format --check . exits 0 and the justfile gate covers the whole tree, or the exclusion and its reason are recorded in ai_docs/runtime.md and the justfile.
- [ ] The reformat lands as its own mechanical commit with no behavior change (tests green).

## Evidence

- Observed by the PR #218 and #219 reviews (80 files then); re-run on 56acf73: ruff format --check . reports 81 files would be reformatted, 270 already formatted.
