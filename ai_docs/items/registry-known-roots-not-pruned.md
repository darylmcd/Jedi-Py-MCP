# registry-known-roots-not-pruned — Prune evicted auto roots

**row:** `registry-known-roots-not-pruned` · **pri:** `Low` · **size:** `S` · **verified:** `b935c2cda00eea0c75a6e613ff7b8f416f543391`

## Anchors

- `src/python_refactor_mcp/workspace_registry.py:131`

## Acceptance

- [ ] An auto-discovered root evicted from the registry no longer appears in `get_known_roots()` or `server_status.known_roots`; explicit roots stay.
- [ ] Test: evict an auto root, assert it is gone from the known and auto sets.

## Evidence

- Found in the registry-concurrency cold review (PRs #211, #213): `_evict_lru` drops the backend but leaves the root in `_known_roots` and `_auto_roots`, so server_status drifts.
