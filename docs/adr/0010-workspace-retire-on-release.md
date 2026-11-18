# ADR 0010 Retire an evicted workspace when its last request releases it

Date 2026-11-17

Status Accepted

## Context

`WorkspaceRegistry` dropped a workspace from its table and shut its backends down in the same step (capacity eviction, `set_roots`, teardown), whether or not a tool call was still running on it. The tool boundary held the backends across the call without telling the registry. The running request then used a closed rope project, and its next Pyright request found the language server dead and restarted it. Nothing owned the restarted process, so it outlived the server's bookkeeping. ADR 0005 deferred "interaction with in-flight requests" when it removed the idle timeout; this decision defines it.

## Decision

- `get_backends` and `implicit_workspace` hand out backends with one lease acquired in the same step as the lookup (under the registry lock, no await between). The tool boundary releases it through `WorkspaceRegistry.release` in its `finally`, which is synchronous and lock-free, so it is safe during cancellation.
- Eviction and `set_roots` unregister the victim at once and mark it retired before any await. An idle victim is shut down immediately, as before. A leased victim is shut down by its last release, in a tracked task. Nothing waits: no request is delayed by another's lease, and capacity accounting for new requests is unchanged.
- Consequence: live workspaces may briefly exceed `MAX_WORKSPACES`, by at most the number of in-flight requests on evicted workspaces. A holder that never releases keeps only its own workspace alive until the server stops. A request for an evicted root starts a fresh workspace.
- `shutdown_all` closes the registry (a request queued on the lock raises `WorkspaceResolutionError` instead of creating a workspace), then stops every backend, leased or retired-but-leased included, and waits for deferred shutdowns already running. It does not wait for holders: on stdio the SDK cancels in-flight handlers before the lifespan ends, and any other holder fails instead of restarting a server.
- `PyrightLSPClient.shutdown` is terminal: it sets a closed flag and takes the restart lock, and a restart re-checks the flag after starting its process. A closed backend never starts another language server.

## Rejected

- Waiting for a lease to drain before evicting: with every workspace leased a new request waits unboundedly (rope calls have no timeout), and the wait blocks lookups of live workspaces behind the registry lock.
- Cancelling the holder: a refactor cancelled mid-write is worse than a brief extra process.

## Migration

Python-internal only: the MCP tool surface, `MAX_WORKSPACES` and the manifest keys are unchanged. Direct callers of `WorkspaceRegistry.get_backends` or `implicit_workspace` must call `release(backends)` when done; `release` raises on an unmatched call. `prewarm` takes no lease. `WorkspaceBackends` compares by identity.
