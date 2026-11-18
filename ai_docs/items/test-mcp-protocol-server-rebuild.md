# test-mcp-protocol-server-rebuild — Share built servers in contract tests

**row:** `test-mcp-protocol-server-rebuild` · **pri:** `Low` · **size:** `S` · **verified:** `b935c2cda00eea0c75a6e613ff7b8f416f543391`

## Anchors

- `tests/contract/test_mcp_protocol.py:219`

## Acceptance

- [ ] Contract tests share a built server per profile (fixture) instead of building about ten servers per run; `test_server_has_version` builds once.

## Evidence

- PR #212 and #214 reviews: each updated test calls `build_server()` per use.
