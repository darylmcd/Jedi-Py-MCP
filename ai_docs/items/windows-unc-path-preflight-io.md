# windows-unc-path-preflight-io — Reject UNC/device paths before filesystem access

**row:** `windows-unc-path-preflight-io` · **pri:** `Low` · **size:** `M` · **verified:** `de4d87d21cacd62dbbabf881188c339d330b98b7`

## Anchors

- `src/python_refactor_mcp/workspace_registry.py:189-205`
- `src/python_refactor_mcp/util/shared.py:128-146`

## Acceptance

- [ ] Confirmed (by test on Windows or by reading) whether `Path.resolve()` / `.exists()` on a UNC or device-namespace path performs network I/O before containment validation.
- [ ] If so: UNC (`\\server\share`) and device (`\\?\UNC\...`, `\\.\...`) paths are rejected with a typed input error before `resolve_workspace_root` or `validate_workspace_path` touch the filesystem, with tests.
- [ ] If not reachable: the finding is documented in `ai_docs/` with the evidence.

## Evidence

- On Windows, any path parameter reaches `Path.resolve()` and marker `.exists()` probes in the workspace boundary before containment is checked; a UNC path can trigger network I/O and NTLM authentication.

## Context

Boundary entry points: `WorkspaceRegistry.resolve_workspace_root` and `validate_workspace_path` (called from `tool_runtime._validate_params`).
