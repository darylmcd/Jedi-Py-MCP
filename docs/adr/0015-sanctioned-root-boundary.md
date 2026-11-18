# ADR 0015 Server-owned sanctioned-root boundary

Date 2026-11-18

Status Proposed (awaiting operator approval; nothing is implemented)

## Context

The server decides which directories a call may touch from the call's own arguments. A path argument selects its workspace by walking up to the nearest `.git` or `pyproject.toml` (`WorkspaceRegistry.resolve_workspace_root`), so any marker-bearing project on disk is reachable, and a server started for project A serves project B. `multi_project_rename` opens a rope `Project` and, with `apply=true`, writes in every `additional_roots` entry it is given, with no check beyond the UNC rule of ADR 0011. ADR 0006 deliberately left "only previously authorized roots" out of scope.

Roslyn-Backed-MCP solved this by making the server own the boundary: `ROSLYNMCP_SANCTIONED_ROOTS`, empty means denied, client roots never widen it (its ADR 0002, `SECURITY.md` section Path Validation, `docs/setup.md` section Configure the filesystem boundary, `ai_docs/references/environment-variables.md`). This ADR adopts that stance with this server's prefix and without its sibling-worktree expansion.

Four open backlog rows are one policy question, "which directories may a call touch?": `multi-project-rename-roots`, `workspace-selection-authorized-roots`, `output-dir-anchorless-boundary`, `implicit-workspace-unlocked-window`.

## Facts verified in this repo (2026-11-18, HEAD 1f06813)

| Question | Finding |
|---|---|
| Does any code read MCP client roots? | No. `src/` has no `roots/list` call and no handler. `WorkspaceRegistry.set_roots` is called once, from `server.py:36`, with the CLI `workspace_root` only. No caller relies on `set_roots` widening access. |
| What is a "known root" today? | The CLI positional root plus roots found by marker discovery (`_auto_roots`). Discovery makes a root known; nothing authorizes it. |
| Boundary order today (`tool_runtime.tool_error_boundary`) | 1 `_reject_relative_paths`, `_reject_network_only_paths` (string checks) -> 2 `_resolve_backends` (resolve root, evict, start Pyright/rope/Jedi, take a lease, mark selected) -> 3 `_validate_params` (containment in the workspace, output dir, identifiers). A call with an invalid identifier already starts backends and selects the workspace. |
| `output_dir` today | Already confined to the call's own workspace: `resolve_workspace_dir` calls `validate_workspace_path(..., workspace_root)` (`util/shared.py:195`). An anchorless call resolves against the sole selected workspace (PR #208). See Open point 1. |
| Link handling today | `validate_workspace_path` uses `Path.resolve()`, which follows symlinks and junctions; the workspace root is resolved the same way. |
| What Claude Code, Codex and Gemini send as MCP roots for a user-scope server | Not verified. It does not matter for authority: this server never requests roots. |
| Relative entries and `.` | `Path(".").resolve()` anchors at the server process's working directory, which the MCP client chooses. Not yet exercised from a client that starts the server outside the project; the Piece A tests must cover it. |

## Decision

**Rule.** Every path a call supplies and the server reads or writes must resolve inside a sanctioned root. Otherwise the call is refused with a typed error before any file is opened, any backend is started, any lock is taken or any workspace is selected.

### Sanctioned roots

| Item | Decision |
|---|---|
| Setting | `PYTHON_REFACTOR_MCP_SANCTIONED_ROOTS`, entries delimited with `os.pathsep` (`;` on Windows, `:` elsewhere). Read once at startup. |
| Relative entry | Resolved against the server's startup directory (`.` is allowed). Resolution happens once at startup, and an entry that does not exist or is not a directory is a startup error naming the setting. |
| Empty or unset | Denied. No fallback to the startup directory. Path-less tools (`server_status`, `list_environments`) keep working. |
| Shipped config | The example client config in `docs/setup.md` sets `"."` explicitly. |
| Client roots | Never read, never widen. If a later change starts consuming client roots, they may only narrow within the sanctioned roots. No narrowing mechanism is built now. |
| Marker discovery | Picks the workspace inside a sanctioned root and never sanctions one. The upward marker walk stops at the sanctioned root that contains the path; if no marker is found inside it, that sanctioned root is the workspace. |
| Expansion | None. Lane worktrees live under the repo's `.worktrees` directory, inside the root. |
| CLI `workspace_root` | A pre-warm hint, never an authority. It must lie inside a sanctioned root, or startup exits naming the setting (same shape as the UNC refusal of ADR 0011). See Open point 2. |

### Path comparison

1. Refuse UNC and device-namespace strings first (ADR 0011, unchanged).
2. Resolve to a real path: follow every symlink and junction in the path and in each root; a nonexistent tail is appended to its resolved existing ancestor.
3. Compare with `os.path.normcase` (case-insensitive on Windows) on whole path components, so `D:\repo2` is not inside `D:\repo`.
4. A path that escapes a root through a link is outside it.
5. The check never touches the filesystem beyond resolution, and a refusal is identical whether or not the path exists.

Scope: caller-supplied paths only. Files Pyright, Jedi and rope read through import resolution (stdlib, site-packages, a venv) are not governed. Time-of-check to time-of-use: an apply re-checks the resolved path of every file it writes (Piece B for `multi_project_rename`; Piece C for the single-workspace write tools).

### The four answers

| Row | Answer |
|---|---|
| `multi-project-rename-roots` | Every `additional_roots` entry must lie inside a sanctioned root, checked before any `Project(root)` opens. "Known to the registry" is not enough. The `additional_roots` entry leaves `_PATH_LIKE_ALLOWLIST` in `tests/unit/test_error_boundary.py`. This is the live write risk and ships first. |
| `workspace-selection-authorized-roots` | No. A call selects only a workspace inside a sanctioned root. A server started for project A refuses a path in unrelated project B unless B is sanctioned. |
| `output-dir-anchorless-boundary` | An absolute `output_dir` must lie inside a sanctioned root. It is not restricted to the call's own workspace. A relative `output_dir` resolves against the call's workspace, and its result must also lie inside a sanctioned root. |
| `implicit-workspace-unlocked-window` | Order: (1) validate parameters, (2) check every path against the sanctioned roots, (3) only then select or create the workspace. Steps 1 and 2 have no side effects. The pure root resolution and the workspace containment check (ADR 0006) run before any backend starts; backend start, lease and selection come last. |

### Which error wins

Parameter validation (step 1) runs before the root check (step 2). A call with an invalid parameter and an unsanctioned path fails with `INVALID_INPUT` and no side effect. A call with valid parameters and an unsanctioned path fails with `SANCTIONED_ROOT`. Both leave the registry unchanged.

### The refusal

One typed error, `SanctionedRootError(ToolInputError)`, code `SANCTIONED_ROOT`, surfaced as `[SANCTIONED_ROOT] ...` like `AMBIGUOUS_WORKSPACE`. It is distinct from `INVALID_INPUT`. Messages are path-free (parameter label and list index only; no path value, no configured roots, no existence hint) and name the setting:

| Case | Message |
|---|---|
| No roots configured | `[SANCTIONED_ROOT] No sanctioned roots are configured, so every path is refused. Set PYTHON_REFACTOR_MCP_SANCTIONED_ROOTS (entries delimited by the OS path separator) and restart the server.` |
| Outside the roots | `[SANCTIONED_ROOT] The path in parameter <label> is outside the sanctioned roots. Add its root to PYTHON_REFACTOR_MCP_SANCTIONED_ROOTS and restart the server.` |

The two cases differ in text and are told apart by the opening sentence ("No sanctioned roots are configured" vs "outside the sanctioned roots"), which tests pin.

## Open points for the approver

1. **`output_dir` becomes looser, not stricter.** Today it is confined to the call's own workspace (table above); answer 3 widens it to any sanctioned root, including an absolute path in another sanctioned workspace and a relative `../other`. A write tool (`create_type_stubs`) can then write into a sibling sanctioned workspace. This ADR drafts your decision as stated. The alternative is to keep the workspace confinement and add only the sanctioned-root check (every sanctioned-root violation is still refused). Say which.
2. **CLI `workspace_root` outside the roots, or roots empty.** Drafted as a startup exit with a message naming the setting. The alternative is to start, skip the pre-warm and log a warning, so the first path call returns the `SANCTIONED_ROOT` refusal.
3. **Marker walk stops at the sanctioned root.** With sanctioned `D:\repo\pkg` and a marker at `D:\repo`, the workspace becomes `D:\repo\pkg` rather than `D:\repo`, which can change which `pyproject.toml` configures it. Drafted to keep every workspace inside the boundary.
4. **Client roots are not consumed at all today**, so "client roots may select or narrow" has no implementation; this ADR states they never widen and builds nothing.

## Migration (breaking; one `changed-breaking-*` fragment per shipped piece)

- Refused now: any path outside the sanctioned roots, every path while the setting is empty, and `multi_project_rename` roots outside them. A server registered once for many repositories (user scope) must have its roots configured, or every path call is refused.
- Configure: `PYTHON_REFACTOR_MCP_SANCTIONED_ROOTS` in the client's server `env`, for example `"."` for a repository-scoped registration or `D:\repos` for a user-scope one. Empty means denied.
- Client roots: users see no change; they were never read.
- Known limits: dynamic hierarchy tricks and backend-internal reads are not governed; a link created between the check and the write is re-checked at apply only for the tools named above.

## Work order (each piece mergeable alone; dependency-chained rows are written on approval)

| Piece | Content | Closes |
|---|---|---|
| A | This ADR, the root set (`config.py`) and one shared path-check function, the `SANCTIONED_ROOT` error, tests; no tool consults it yet. | none |
| B | `multi_project_rename` write guard (answer 1), apply-time re-check, allow-list entry removed. | `multi-project-rename-roots` |
| C | Workspace selection (answer 2) and boundary reordering (answer 4), registry marker walk bounded, CLI `workspace_root` rule, example config in `docs/setup.md`. | `workspace-selection-authorized-roots`, `implicit-workspace-unlocked-window` |
| D | `output_dir` (answer 3). | `output-dir-anchorless-boundary` |

Red-first tests per piece are listed in the operator decision; each fails on current `main`. Piece B is taken first if anything is.

## References

- Roslyn-Backed-MCP `docs/decisions/0002-configured-sanctioned-root-boundary.md`, `SECURITY.md`, `docs/setup.md`, `ai_docs/references/environment-variables.md`; its open row `sanctioned-root-refusal-names-no-remedy` (the lesson behind the message text above).
- ADR 0004 (refuse unless every occurrence is accounted for), ADR 0006, ADR 0011, ADR 0001 (contract-care).
