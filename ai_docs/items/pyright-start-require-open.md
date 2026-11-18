# pyright-start-require-open — PyrightLSPClient.start does not check the backend is open

**row:** `pyright-start-require-open` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py:417`
- `src/python_refactor_mcp/backends/pyright_lsp.py:439`
- `src/python_refactor_mcp/workspace_registry.py:100`

## Acceptance

- [ ] Calling start() after shutdown() raises PyrightError and spawns no process (asserted with a spy on the client factory).
- [ ] A unit test covers the start-after-shutdown path.

## Evidence

- Found by the PR #216 cold review (retire on release). Re-derived on 56acf73: PyrightLSPClient.start (pyright_lsp.py:417) has no _closed check; WorkspaceBackends.initialize (workspace_registry.py:91) only guards on _initialized.
