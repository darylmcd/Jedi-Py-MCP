# ADR 0007 Explicit workspace selection for path-less calls

Date 2026-11-17

Status Accepted

## Context

A tool call that named no file (`search_symbols`, `fix_module_names`, `undo_refactoring`, the change-stack tools, `get_workspace_diagnostics`, ...) was answered by the most recently used workspace, or by the CLI pre-warm root when none had been used. A user-scope registration with one positional root, shared by every repository, therefore answered path-less calls from another repository's checkout, and a mutating call (`fix_module_names` with `apply=true`, undo, redo) changed the wrong workspace. The server could not tell a workspace the caller chose from one it merely had warm.

## Decision

A call that names no workspace never infers one by recency or by startup configuration.

- **Selector.** Every tool that can be called without a required path accepts an absolute `root_path`: the workspace root or any path inside it, resolved by the same marker walk as `file_path` (ADR 0002). It is one more workspace-selecting path: it must be absolute, lie in one workspace together with the call's other paths (ADR 0006), and is redundant when it lies in the same workspace as the other paths (a `root_path` in a different workspace is rejected with the multi-workspace error). `dead_code_detection`, `get_symbol_outline`, `get_workspace_diagnostics` and `unused_symbol_sweep` already had `root_path` as a scan directory; it now also selects the workspace.
- **Selected workspace.** A workspace is selected when a path-bearing request chose it. The startup pre-warm (the positional `workspace_root` argument) starts its backends but leaves the workspace unselected.
- **Implicit resolution.** A path-less call resolves implicitly only to the sole live workspace that a path-bearing request already selected. This includes mutating calls (`fix_module_names` with `apply=true`, undo, redo, the change-stack tools): the stricter alternative of requiring `root_path` whenever `apply=true` is rejected here, because the workspace was chosen by this session's own path-bearing call; any stricter policy about which roots may be selected belongs to the open `workspace-selection-authorized-roots` work. Use of the workspace refreshes its least-recently-used position.
- **Ambiguity.** Otherwise (several live workspaces, only the pre-warmed workspace, or none) the call fails with the coded error `[AMBIGUOUS_WORKSPACE]`, which lists the live roots, marks a pre-warmed root as "pre-warmed, not selected", and names `root_path`. No backend starts and no tool body runs.
- **Consequence for single-project registrations.** With a positional root, the first path-less call fails until a path-bearing call or `root_path` selects that root. The positional root is a Pyright warm-up for that project, not a default workspace. Registrations shared by several repositories should omit it.
- **No workspace needed.** `server_status` reports server state, needs no workspace and works with none live. `diff_preview` resolves only a workspace root (it never starts backends) and does not select a workspace.
- **Empty selector lists.** `test_impact_select` takes no `root_path` and selects its workspace through `symbols[].file_path`, so an empty `symbols` list, which selects nothing, is now rejected (`minItems: 1`) instead of reaching an ambiguity error that the tool could not resolve.

## Migration

- Pass an absolute `root_path` on path-less calls, or make one path-bearing call (any tool with `file_path`, `file_paths`, `source_file`, ...) first so the workspace is selected.
- Drop the positional `workspace_root` from registrations shared by several repositories; keep it only for single-project registrations, knowing it does not answer path-less calls by itself.
- Callers of `test_impact_select` must pass at least one symbol anchor.
- Handle `[AMBIGUOUS_WORKSPACE]` like `[INVALID_INPUT]`: it is a caller-input error and is not retried with the same arguments.
- Direct Python callers of `WorkspaceRegistry` lose `get_most_recent()`; `implicit_workspace()` replaces it and `prewarm()` replaces the eager `get_backends()` used at startup.
