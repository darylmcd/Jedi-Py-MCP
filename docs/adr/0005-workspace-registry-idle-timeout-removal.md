# ADR 0005 Remove the unused workspace idle timeout

Date 2026-11-17

Status Accepted

## Context

`WorkspaceRegistry.__init__` accepted `idle_timeout_seconds` and stored it, but nothing ever read it. No documentation, environment variable or manifest setting described an idle lifecycle, and the server constructs the registry with `max_workspaces` only. The parameter promised behavior the registry does not have.

## Decision

Remove the parameter instead of implementing idle eviction. Capacity eviction (`MAX_WORKSPACES`, auto-discovered workspaces first, then least recently used) is the only workspace lifecycle policy. An idle lifecycle would need a background reaper, a new setting and defined interaction with in-flight requests, and none of that is specified. It can be proposed later as its own decision.

## Migration

Direct Python callers should drop `idle_timeout_seconds=...` from `WorkspaceRegistry(...)`; passing it now raises `TypeError`. The MCP tool surface, `MAX_WORKSPACES` and the manifest are unchanged in this respect.
