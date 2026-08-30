# security-scan-silent-file-drop — security_scan reports unparseable files as clean

**row:** `security-scan-silent-file-drop` · **pri:** `Medium` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/tools/metrics/security.py` (`_scan_file`, line 37)
- `tests/unit/test_metrics_tools.py` (new file — the metrics scanners have no dedicated unit-test module today)

## Acceptance

- [ ] A file that raises `OSError`/`SyntaxError` during `_scan_file` is reported to the caller as skipped, not silently omitted.
- [ ] `security_scan` surfaces skipped files using the existing `BackendFailure` model rather than a new convention.
- [ ] Unit test proves an unparseable file yields a caller-visible skip signal and is NOT indistinguishable from a clean scan.

## Evidence

- doc-audit bad-code-surfacing 2026-08-30. `_scan_file` returns `[]` on `except (OSError, SyntaxError)` with no signal, so a file that fails to parse is reported identically to a file with zero security findings. Highest-severity member of the silent-file-drop family because the false negative is a security result.

## Context

- Same regression shape already fixed in `tools/search/{dead_code,structural,symbols,unused_symbols}.py`, `src/python_refactor_mcp/tools/metrics/dependencies.py`, and `src/python_refactor_mcp/tools/refactoring/circular_imports.py` (PRs #83, #90, #92). The fix was never generalized to the `metrics/` family. Reference implementation to copy: `src/python_refactor_mcp/tools/search/symbols.py` (reference only — not an edit target for this row). Split out from the wider family because a silent security false-negative warrants its own priority.
