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
  Area: tool implementation
  Item: Implement Stage 4 analysis, navigation, and refactoring tools with backend orchestration.
  Why it matters: MCP tool surface is still placeholder-only even though backends are available.
  Verification needed: Tool unit tests exist and `tests/unit/` passes with fallback behavior validated.

- Status: `open`
  Area: integration testing
  Item: Add Stage 5 integration test fixture project and end-to-end MCP server tests.
  Why it matters: backends are implemented, but no integration safety net verifies tool behavior through MCP transport.
  Verification needed: `python -m pytest tests/integration/ -v` passes on a prepared environment.

- Status: `open`
  Area: packaging
  Item: Implement Stage 6 packaging and executable build flow in `scripts/build.ps1`.
  Why it matters: deployment path is still placeholder and undocumented for production use.
  Verification needed: build script produces a working executable and README build instructions are current.