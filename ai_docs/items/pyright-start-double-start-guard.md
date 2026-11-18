# pyright-start-double-start-guard — PyrightLSPClient.start twice replaces the client unshut

**row:** `pyright-start-double-start-guard` · **pri:** `Low` · **size:** `S` · **verified:** `d390a382462fa0905eb6b9aae9c716a628ad6549`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py:442`

## Acceptance

- [ ] A second start() never leaks the first process (test with a client factory spy).

## Evidence

- Found by the PR #226 and #227 reviews; deliberately left out of #227 because it needs a policy choice.
