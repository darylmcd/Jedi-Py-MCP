# sanctioned-roots-workspace-selection — Workspace selection inside sanctioned roots, validate-then-select order (piece C)

**row:** `sanctioned-roots-workspace-selection` · **pri:** `Medium` · **size:** `L` · **verified:** `102c7e0efba2ffe588c84366741d7e9de10eb546` · **deps:** `sanctioned-roots-multi-project-rename`

## Anchors

- `src/python_refactor_mcp/tool_runtime.py:440`
- `src/python_refactor_mcp/workspace_registry.py`
- `src/python_refactor_mcp/server.py:36`
- `src/python_refactor_mcp/__main__.py`

## Acceptance

- [ ] tool_error_boundary order: validate parameters, check every path against the roots, resolve the root purely and check workspace containment, only then start backends, lease and select. Invalid parameters plus an unsanctioned path fail with INVALID_INPUT and no side effect (test).
- [ ] A path in an unsanctioned project is refused; no backend started, registry unchanged (test). A client root outside the sanctioned roots grants nothing (test).
- [ ] The marker walk stops at the sanctioned root; with no marker inside it the sanctioned root is the workspace, the parent config is not read, and server_status shows root_source per workspace (test).
- [ ] Empty roots at startup, or CLI workspace_root outside the roots: the server starts, skips the pre-warm, prints one stderr line, server_status reports sanctioned_roots {configured, count} without paths, and the first path call is refused with the matching message (tests).
- [ ] docs/setup.md and the migration note cover user-scope registration and the sanction-the-project-root advice; changed-breaking-* fragment.
- [ ] ADR 0015 (docs/adr/0015-sanctioned-root-boundary.md), section Tests, is the test list; every test is red on main before the piece.

## Evidence

- ADR 0015 answers 2 and 4. Cause of the old ordering defect: _resolve_backends runs before _validate_params, so a rejected call has already started Pyright and selected a workspace (supersedes workspace-selection-authorized-roots and implicit-workspace-unlocked-window).
