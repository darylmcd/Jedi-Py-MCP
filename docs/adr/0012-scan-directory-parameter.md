# ADR 0012 Scan directory is `directory`; `root_path` only selects a workspace

Date 2026-11-18

Status Accepted

## Context

`root_path` carried two jobs depending on the tool. On 26 tools it only selected a workspace (ADR 0007). On four tools (`get_workspace_diagnostics`, `get_symbol_outline`, `dead_code_detection`, `unused_symbol_sweep`) it was also the directory to scan, so a subdirectory passed only to name a workspace silently narrowed the scan, and a subdirectory passed to scope a scan also chose the workspace that contains it. ADR 0007 recorded the overload without resolving it.

## Decision

Each parameter name has one meaning across the whole tool surface.

- **`root_path`** only selects a workspace: the workspace root or any path inside it, resolved by the marker walk of ADR 0002. It never changes what a tool scans.
- **`directory`** exists on exactly four tools. It keeps both roles those tools always had: it is the absolute directory to scan, and it anchors the workspace (the one containing it, found like `file_path`). It defaults to the workspace root. The rename gives the scan its own name; it does not remove the anchoring.
- **Rejection.** The four tools no longer accept `root_path`. A request that sends it (alone or beside `directory`) fails argument validation with a message that names `directory` and this ADR. The error is raised inside the SDK argument model, before the tool boundary, so it carries no `[CODE]` prefix and callers must match the text, not a code. No alias is kept: accepting `root_path` as a scan scope would silently widen scans that used to be narrowed.
- **Boundary rules.** `directory` is in `PATH_PARAMS`: absolute only, UNC and device paths refused (ADR 0011), selects the workspace together with the call's other paths (ADR 0006: all must lie in one workspace), and must lie inside the selected workspace. A relative `directory` is rejected naming `parameter: directory`.
- **Nested projects.** A `directory` that is, or lies inside, a nested project (its own `.git`, `pyproject.toml`, `setup.py` or `setup.cfg`) selects that nested workspace (ADR 0002) and the scan runs there. This is deliberate: the selected workspace contains the scanned directory, so the scan cannot leave it. A `directory` with no enclosing workspace fails workspace resolution. When `file_path` or `file_paths` is also given, the file scope wins over `directory` for what is scanned, and all paths must still lie in one workspace; a `directory` outside the workspace a file path selected fails the containment check.
- **Ambiguity message.** `[AMBIGUOUS_WORKSPACE]` names `root_path` and says the four scan tools take `directory` instead.

## Migration

- On `get_workspace_diagnostics`, `get_symbol_outline`, `dead_code_detection` and `unused_symbol_sweep`, rename the `root_path` argument to `directory`. To scan the whole workspace, pass the workspace root as `directory` or omit it after a path-bearing call has selected the workspace.
- Every other tool keeps `root_path` unchanged.
- Do not retry a rejected `root_path` call unchanged; match the rejection by its text.
- Supersedes the scan-directory sentence of ADR 0007's Selector bullet.
