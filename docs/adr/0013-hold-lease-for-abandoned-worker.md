# ADR 0013 Hold the workspace lease until an abandoned worker thread finishes

Date 2026-11-18

Status Accepted

## Context

ADR 0010 retires an evicted workspace when its last request releases its lease. A request runs rope and Jedi work through `run_in_thread` (`asyncio.to_thread` under `wait_for`). A cancelled caller or an expired timeout cancels only the asyncio wrapper: the thread cannot be stopped and keeps running. The tool boundary then released the request lease at once, so a retired workspace was shut down (rope project closed, `_project` set to `None`) under a running worker. Reproduced on 029b683 for both cancellation and timeout.

## Decision

- `run_in_thread` shields its worker task. Cancelling the caller or timing out abandons the wait, never the task, so the thread is not cancelled.
- When a `worker_lease_scope` is set (`tool_error_boundary` sets it for each call that holds backends), `run_in_thread` borrows one extra lease before dispatch and releases it from the worker task's done-callback, exactly once, through `WorkspaceRegistry.release`. A retired workspace is therefore shut down only after both the request and the worker have released.
- The lease is released when the worker task completes, which is when the thread returns, with one exception: event-loop teardown cancels the task while its thread may still run. That is acceptable because server teardown goes through `shutdown_all`, which does not wait for holders.
- A worker still queued when its caller leaves is skipped instead of run (a mutating `apply=True` operation must not run after its caller is gone). A worker already running finishes.
- `shutdown_all` is unchanged: it force-stops leased backends and never waits for workers, so a stuck rope operation cannot hang server stop. A late worker release after teardown starts nothing.
- ADR 0010's bound on live backends widens: evicted workspaces may also stay alive for the worker threads their cancelled or timed-out requests left running.

## Rejected

- Waiting for workers in `shutdown_all` or before retiring: rope operations have no hard bound, so teardown could hang.
- Injecting a lease into `RopeBackend` and `JediBackend` constructors and changing every call site: about 57 call sites and every test constructor change, for the same behaviour a context variable gives.

## Migration

Python-internal only: the MCP tool surface, error codes and manifest are unchanged, so this is not a breaking change. `run_in_thread` keeps its signature; backends called outside the tool boundary borrow nothing. Known remaining gaps, tracked separately: `shutdown_all` still closes rope under a running worker, and a timed-out worker can overlap the next rope call on the same project.
