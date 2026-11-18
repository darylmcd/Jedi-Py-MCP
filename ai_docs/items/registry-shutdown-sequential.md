# registry-shutdown-sequential — Isolate per-backend shutdown failures

**row:** `registry-shutdown-sequential` · **pri:** `Low` · **size:** `S` · **verified:** `b935c2cda00eea0c75a6e613ff7b8f416f543391`

## Anchors

- `src/python_refactor_mcp/workspace_registry.py:49`

## Acceptance

- [ ] A non-Exception failure while shutting down one backend does not skip shutting down the remaining backends.
- [ ] Test with a backend whose shutdown raises a BaseException subclass.

## Evidence

- #211 cold review: `_shutdown_all` awaits each backend in sequence and `_release_resources` swallows only Exception, so a BaseException from one backend skips the rest.
