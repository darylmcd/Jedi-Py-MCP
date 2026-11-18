# shutdown-all-closes-rope-under-worker — shutdown_all closes rope under a running worker

**row:** `shutdown-all-closes-rope-under-worker` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/workspace_registry.py:123`
- `src/python_refactor_mcp/backends/rope_backend.py:602`
- `src/python_refactor_mcp/backends/rope_backend.py:613`

## Acceptance

- [ ] A test shows shutdown_all with a running rope worker neither crashes the worker nor leaves a closed project in use, or documents and bounds the drain.
- [ ] The decision versus ADR 0010 'does not wait for holders' is recorded in an ADR addendum.

## Evidence

- Raised by the threading-lease plan and cold review (ADR 0013, PR #225): shutdown_all stays non-waiting, so rope.close() sets _project to None under a running worker (rope_backend.py:613).
