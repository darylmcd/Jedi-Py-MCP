# active-tool-profile-import-time — Discover the tool profile at build time

**row:** `active-tool-profile-import-time` · **pri:** `Low` · **size:** `S` · **verified:** `b935c2cda00eea0c75a6e613ff7b8f416f543391`

## Anchors

- `src/python_refactor_mcp/server.py:46`

## Acceptance

- [ ] The advertised tool profile is read when the server is built (`build_server`), not at import time; tests set the profile without reloading modules.

## Evidence

- `_ACTIVE_TOOL_PROFILE = discover_tool_profile()` is an import-time env read, the same hidden-state class that PR #212 removed for the workspace root.
