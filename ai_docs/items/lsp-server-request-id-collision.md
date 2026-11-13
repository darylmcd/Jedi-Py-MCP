# lsp-server-request-id-collision — Route server requests before matching response IDs

**row:** `lsp-server-request-id-collision` · **pri:** `Medium` · **size:** `S` · **verified:** `7167e37ab6bce5e59dc547587724e3bda8eec6e9`

## Anchors

- `src/python_refactor_mcp/util/lsp_client.py:225-246`
- `tests/unit/test_pyright_lsp.py`

## Acceptance

- [ ] A server request with the same ID as a pending client request is answered while the client future waits for its response.

## Evidence

- The transport checks the pending client map before classifying a server method. An incoming server request can share an ID with a client request.
