# metrics-scanner-silent-file-drop — metrics scanners silently skip unparseable files

**row:** `metrics-scanner-silent-file-drop` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tools/metrics/architecture.py` (line 101)
- `src/python_refactor_mcp/tools/metrics/complexity.py` (line 72)
- `src/python_refactor_mcp/tools/metrics/coverage.py` (line 28)
- `src/python_refactor_mcp/tools/metrics/duplicates.py` (line 38)
- `tests/unit/test_metrics_tools.py` (new file — shared with `security-scan-silent-file-drop`)

## Acceptance

- [ ] Each of the four scanners reports per-file `SyntaxError`/`OSError` skips to the caller instead of bare `continue`.
- [ ] Skip reporting reuses the existing `BackendFailure`/skipped-file shape rather than introducing a fourth convention.
- [ ] Unit test per scanner proves an unparseable file produces a caller-visible skip rather than silently shrinking the result set.

## Evidence

- doc-audit bad-code-surfacing 2026-08-30. All four catch `(SyntaxError, OSError)` and `continue`, so metrics computed over a partially-unreadable tree are silently based on fewer files than the caller believes.

## Context

- Sibling slice of `security-scan-silent-file-drop`. Same regression shape as the already-remediated `search/` family (PRs #83, #90, #92); scoped to 4 production files to stay inside the row-size contract.
