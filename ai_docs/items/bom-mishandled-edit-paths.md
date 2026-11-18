# bom-mishandled-edit-paths — UTF-8 BOM files are mishandled by edit and write paths

**row:** `bom-mishandled-edit-paths` · **pri:** `Medium` · **size:** `L` · **verified:** `56acf734d43c24c331918b47ac75a7fbe6956ad4`

## Anchors

- `src/python_refactor_mcp/util/diff.py:112`
- `src/python_refactor_mcp/backends/rope_backend.py:689`
- `src/python_refactor_mcp/backends/rope_backend.py:648`
- `src/python_refactor_mcp/tools/refactoring/format.py:78`
- `src/python_refactor_mcp/tools/refactoring/docstrings.py:392`
- `src/python_refactor_mcp/util/cst_apply.py:71`

## Acceptance

- [ ] A byte-exact test per writer (rope apply, apply_text_edits, format_code, docstring_sync, CST apply) shows a leading BOM survives, including on LF-only files.
- [ ] Line-0 character offsets on a BOM file match the BOM-free file.

## Evidence

- Found in the rope-apply-crlf reviews (merged as PR #222); anchors are the read and write sites on 56acf73. Re-derived on 56acf73 by running the writers on a BOM file: format_code, docstring_sync and CST apply drop the BOM (ruff format and libcst strip it); apply_lint_fixes and apply_text_edits keep it, and change_signature on a BOM file now raises a typed ToolInputError (PR #218), so those three are not defects here. test_line_endings.py only compares the CRLF result to the LF result, so it passes while the BOM is dropped in both.

## Notes

Size L: the BOM writers (format.py, docstrings.py, cst_apply.py, diff.py) share one decision (what a BOM round-trips as) and must land together.
