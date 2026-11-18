# workspace-selection-authorized-roots — Restrict path-selected workspaces to authorized roots

**row:** `workspace-selection-authorized-roots` · **pri:** `Medium` · **size:** `M` · **verified:** `de4d87d21cacd62dbbabf881188c339d330b98b7`

## Anchors

- `src/python_refactor_mcp/tool_runtime.py:216-230`
- `src/python_refactor_mcp/workspace_registry.py:189-205`
- `docs/adr/0006-nested-path-boundary.md`

## Acceptance

- [ ] Operator decision recorded (ADR): may a call select a workspace outside previously registered/pre-warmed roots?
- [ ] Per the decision, a path under an unregistered marker-bearing project is rejected with a typed input error before any backend starts.
- [ ] Test: server started for workspace A rejects a call naming a file in unrelated project B.
- [ ] Changelog fragment `changed-breaking-*` plus migration note if behavior is restricted.

## Evidence

- A path tool call selects its workspace from its own first path (nearest `.git`/`pyproject.toml` marker via `resolve_workspace_root`), so a call can name a file in any marker-bearing project on disk even when the server was started for another workspace. Left open by PR #202 (ADR 0006).

## Context

Operator decision needed first. Related: `bl-0056`.
