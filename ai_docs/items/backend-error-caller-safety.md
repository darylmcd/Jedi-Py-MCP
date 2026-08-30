# backend-error-caller-safety — Redact backend failures at the MCP boundary

**row:** `backend-error-caller-safety` · **pri:** `High` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tool_runtime.py` (`tool_error_boundary`)
- `src/python_refactor_mcp/errors.py` (`BackendError` contract)
- `src/python_refactor_mcp/util/cst_apply.py` and refactoring callers that append raw `OSError` / parser text
- `tests/unit/test_error_boundary.py`

## Acceptance

- [ ] MCP `ToolError` responses retain a stable typed code and actionable safe summary without absolute paths, provider/vendor prose, or raw exception payloads.
- [ ] Full internal diagnostics remain available through structured, redacted logging without echoing source content or credentials.
- [ ] Regression tests cover Windows and POSIX paths, multiline provider errors, and secret-shaped payloads.

## Evidence

- Adjacent review found `tool_error_boundary` forwards `str(BackendError)` verbatim while CST/refactoring producers interpolate raw OS/parser exceptions and file paths.
