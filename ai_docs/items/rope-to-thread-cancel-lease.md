# rope-to-thread-cancel-lease — Cancelled handler frees the lease while rope thread still runs

**row:** `rope-to-thread-cancel-lease` · **pri:** `Medium` · **size:** `M` · **verified:** `56acf734d43c24c331918b47ac75a7fbe6956ad4`

## Anchors

- `src/python_refactor_mcp/backends/_threading.py:47`
- `src/python_refactor_mcp/workspace_registry.py:222`
- `src/python_refactor_mcp/tool_runtime.py:478`

## Acceptance

- [ ] A test cancels a handler awaiting a blocked rope worker and shows the backends are not shut down or closed until the worker returns.
- [ ] After the worker returns the lease is released exactly once and a retired workspace is shut down.

## Evidence

- Raised by the PR #216 reviews: asyncio.to_thread cancellation abandons the thread, yet the wrapper finally releases the lease at once. Re-derived on 56acf73: run_in_thread (_threading.py:47-48) awaits wait_for(to_thread) with no shield, and tool_runtime.py:478 releases in the wrapper finally.
