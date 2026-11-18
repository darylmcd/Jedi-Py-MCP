# path-resolve-triple-copy — directory resolve-or-default logic copied three times

**row:** `path-resolve-triple-copy` · **pri:** `Low` · **size:** `M` · **verified:** `56acf734d43c24c331918b47ac75a7fbe6956ad4`

## Anchors

- `src/python_refactor_mcp/tools/analysis/diagnostics.py:101`
- `src/python_refactor_mcp/tools/search/_helpers.py:151`
- `src/python_refactor_mcp/tools/navigation/outline.py:206`

## Acceptance

- [ ] One helper holds the resolve-or-default expression and all three call sites use it.
- [ ] Existing tests pass, and a test covers the helper for empty, absolute and missing-directory input.

## Evidence

- Found in the root-path-meaning plan review (the parameter was renamed root_path to directory for these tools afterwards); exact copies are diagnostics.py:101 and _helpers.py:151, with outline.py:206 a variant.
