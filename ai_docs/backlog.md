# Backlog

Open follow-up items only. Remove entries once verified complete.

Template:

- Status: `open`
  Area:
  Item:
  Why it matters:
  Verification needed:

Current open items:

- Status: `open`
  Area: integration tests
  Item: Add end-to-end integration smoke test coverage for `introduce_parameter`.
  Why it matters: The implementation exists and has unit coverage, but no MCP transport integration test validates real invocation behavior.
  Verification needed: Add a test in `tests/integration/test_end_to_end.py` that calls `introduce_parameter` with `apply=false` and asserts non-error structured output.

- Status: `open`
  Area: integration tests
  Item: Add end-to-end integration smoke test coverage for `encapsulate_field`.
  Why it matters: The implementation exists and has unit coverage, but no MCP transport integration test validates real invocation behavior.
  Verification needed: Add a test in `tests/integration/test_end_to_end.py` that calls `encapsulate_field` with `apply=false` and asserts non-error structured output.

- Status: `open`
  Area: integration tests
  Item: Expand failure-path integration scenarios to include bad line/position and invalid rename target flows.
  Why it matters: Current failure-path integration coverage checks invalid direction and missing file only; additional error paths from the plan are still not covered.
  Verification needed: Add assertions for MCP `isError=true` responses for invalid line/character and rename-preflight/rename invalid cases.

- Status: `open`
  Area: documentation
  Item: Complete prompt example bank coverage for all existing tools in the MCP checklist.
  Why it matters: The checklist contains examples for selected tools, but not a complete per-tool prompt bank as planned.
  Verification needed: Ensure `ai_docs/domains/python-refactor/mcp-checklist.md` includes goal/validation/chaining examples for every registered tool.

- Status: `open`
  Area: unit tests
  Item: Finish invalid-input unit-test coverage for tools that still lack explicit invalid-argument tests.
  Why it matters: Plan called out sparse invalid-input coverage; this remains partially complete.
  Verification needed: Add targeted negative tests and confirm `python -m pytest tests/unit/ -v` remains green.