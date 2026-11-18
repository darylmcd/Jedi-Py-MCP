# tool-records-split-server-registry — One tool record table

**row:** `tool-records-split-server-registry` · **pri:** `Low` · **size:** `M` · **verified:** `93cd1b324525daf60c5666c8f1107db9ce846b21`

## Anchors

- `src/python_refactor_mcp/server.py:440-452`
- `src/python_refactor_mcp/tool_registry.py:1721`
- `src/python_refactor_mcp/tool_registry.py:25`

## Acceptance

- [ ] All tool delegates and their `ToolRecord`s live in one place (`tool_registry.py` `TOOL_RECORDS`); `EXPLICIT_TOOL_RECORDS` and the `extra_records` plumbing in `build_tools`/`tool_names_for_profile` are removed.
- [ ] The tool surface (names, schemas, annotations, profile membership) is byte-identical: contract tests unchanged and green.
- [ ] Module docstring at `tool_registry.py:25` no longer describes the split.

## Evidence

- Delegates for `get_completions`, `get_inlay_hints`, `get_symbol_outline`, `argument_normalizer`, `argument_default_inliner`, `find_unused_imports`, `get_test_coverage_map`, `security_scan`, `security_autofix`, `structural_replace` are defined in `server.py` and registered through `EXPLICIT_TOOL_RECORDS`, away from `TOOL_RECORDS`: two registries, one boundary.

## Context

- Found while planning `bl-0056`; the split forces PR B to edit both files for the same `root_path` change. Pure refactor; no behaviour change.
