# newline-handling-duplicates — Newline normalisation copied across writers; guard skipped

**row:** `newline-handling-duplicates` · **pri:** `Low` · **size:** `L`

## Anchors

- `src/python_refactor_mcp/util/cst_apply.py:71`
- `src/python_refactor_mcp/tools/refactoring/docstrings.py:392`
- `src/python_refactor_mcp/tools/refactoring/format.py:90`
- `src/python_refactor_mcp/tools/refactoring/lint_fix.py:104`
- `src/python_refactor_mcp/util/diff.py:22`

## Acceptance

- [ ] The CRLF-and-CR replace chain exists once (diff._normalize_newlines) and cst_apply and docstrings call it.
- [ ] format_code and apply_lint_fixes refuse to overwrite a file changed since it was read, with a test per tool.

## Evidence

- Found by the rope-apply-crlf cold review: the same normalisation is copied and two ruff writers use unguarded write_atomic. Re-derived on 56acf73: PR #222 added diff._normalize_newlines (diff.py:22, used at diff.py:201) but cst_apply.py:71 and docstrings.py:392 still inline the chain; format.py:90 and lint_fix.py:104 still call write_atomic.

## Notes

Size L: the duplicated newline normalisers must converge on util/diff._normalize_newlines in one change or a caller keeps a divergent copy.
