# server-module-global-workspace-root — Thread the CLI root through the lifespan

**row:** `server-module-global-workspace-root` · **pri:** `Low` · **size:** `S` · **verified:** `93cd1b324525daf60c5666c8f1107db9ce846b21`

## Anchors

- `src/python_refactor_mcp/server.py:66`
- `src/python_refactor_mcp/server.py:72-91`
- `src/python_refactor_mcp/server.py:474-481`

## Acceptance

- [ ] No module-global `_workspace_root`; `run_server` passes the root to the lifespan through a closure/partial or server config, and the `# noqa: PLW0603` is gone.
- [ ] Two servers built in one process with different roots do not share state (test).

## Evidence

- `run_server` mutates the module-level `_workspace_root` (`global` + `noqa: PLW0603`) which `app_lifespan` reads; hidden global state and a suppression.

## Context

- Found while planning `bl-0056`; see `D:/Jedi-Py-MCP/.worktrees/bl-0056.report.md`. Touches the same lifespan lines as bl-0056 PR B; whichever lands second rebases.
