# ADR 0006 Nested path boundary

Date 2026-11-17

Status Accepted

## Context

The tool error boundary validated scalar path parameters, `file_paths` and `refactor_transaction` step paths. Paths nested in other list parameters (`diff_preview` `edits[].file_path`, `test_impact_select` `symbols[].file_path`) and the scalar `stub_file` were not validated, so `diff_preview` read and diffed any readable file and disclosed its content.

## Decision

Validate every caller path at the boundary before the tool runs. Nested `file_path` values (`NESTED_PATH_PARAMS` and transaction steps) and `stub_file` follow the rules of `file_path`: absolute, one workspace (ADR 0002), contained after symlink and `..` resolution, and rewritten to the resolved path. The workspace is the one derived from the call's own explicit paths, as for every other path tool; a stricter policy of only previously authorized roots is out of scope. A drift test fails when a tool adds a path-like parameter the boundary does not cover.

## Migration

Pass absolute in-workspace paths in `edits`, `symbols` and `stub_file`, one call per workspace. Relative, outside-workspace, escaping or multi-workspace paths are rejected with `[INVALID_INPUT]` before any file is read. Returned paths and `test_impact_select` node IDs use the resolved spelling.
