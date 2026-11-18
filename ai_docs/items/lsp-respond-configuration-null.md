# lsp-respond-configuration-null — Answer server requests per method

**row:** `lsp-respond-configuration-null` · **pri:** `Low` · **size:** `S` · **verified:** `93cd1b324525daf60c5666c8f1107db9ce846b21`

## Anchors

- `src/python_refactor_mcp/util/lsp_client.py:219-227`
- `src/python_refactor_mcp/util/lsp_client.py:237-240`

## Acceptance

- [ ] Server-initiated requests are answered per method: `workspace/configuration` returns a list with one entry (null or the configured settings) per `params.items` element; every other method keeps `null`.
- [ ] A test sends a `workspace/configuration` request with N items and asserts the response `result` is a list of length N; a request with no/invalid `items` gets an empty list.
- [ ] Other methods (`client/registerCapability`, `window/workDoneProgress/create`) still answered `null`.

## Evidence

- `_route_message` answers every server request via `_respond(id, result=None)`; LSP defines the `workspace/configuration` result as an array matching `params.items`, so a null result is a protocol violation.

## Context

- Found while reviewing PR #203 (id-collision fix); pre-existing behaviour, not introduced by it.
