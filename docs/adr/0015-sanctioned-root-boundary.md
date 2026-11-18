# ADR 0015 Server-owned sanctioned-root boundary

Date 2026-11-18

Status Accepted (operator approval 2026-11-18; implementation tracked by rows A to D)

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
| `output_dir` today | Already confined to the call's own workspace: `resolve_workspace_dir` calls `validate_workspace_path(..., workspace_root)` (`util/shared.py:195`). An anchorless call resolves against the sole selected workspace (PR #208). Ruling 1 keeps this confinement. |
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
| Client roots | The server does not request MCP roots and builds nothing for them. If support is ever added, client roots may select or narrow within the sanctioned roots and never widen them. |
| Marker discovery | Picks the workspace inside a sanctioned root and never sanctions one. The upward marker walk stops at the sanctioned root that contains the path. When the walk reaches the boundary without finding a marker, that sanctioned root is the workspace, and the server says so: `server_status` lists, per live workspace, `root_source` = `marker` or `sanctioned_root`. Sanction the project root, not a subpackage, if its configuration should apply. |
| Expansion | None. Lane worktrees live under the repo's `.worktrees` directory, inside the root. |
| CLI `workspace_root` | A pre-warm hint, never an authority. When it lies outside the sanctioned roots, or the roots are empty, the server still starts, skips the pre-warm, writes one line to stderr naming the condition, and refuses path calls with `SANCTIONED_ROOT`. A startup exit would show the user only "connection closed". |
| Status | `server_status` reports `sanctioned_roots`: `{configured: bool, count: int}`. Never the paths. |

### Path comparison

1. Refuse UNC and device-namespace strings first (ADR 0011, unchanged).
2. Resolve to a real path: follow every symlink and junction in the path and in each root; a nonexistent tail is appended to its resolved existing ancestor.
3. Compare with `os.path.normcase` (case-insensitive on Windows) on whole path components, so `D:\repo2` is not inside `D:\repo`.
4. A path that escapes a root through a link is outside it.
5. The check never touches the filesystem beyond resolution, and a refusal is identical whether or not the path exists.

Scope: the boundary governs the paths a call supplies. Backend-internal reads are outside it: the interpreter, site-packages, typeshed, Pyright's own files and anything Pyright, Jedi or rope read through import resolution. Roslyn's SDK references are outside its boundary the same way. "Every path" in the rule means every path in the call's arguments, not every file the process opens. Time-of-check to time-of-use: an apply re-checks the resolved path of every file it writes (Piece B for `multi_project_rename`; Piece C for the single-workspace write tools).

### The four answers

| Row | Answer |
|---|---|
| `multi-project-rename-roots` | Every `additional_roots` entry must lie inside a sanctioned root, checked before any `Project(root)` opens. "Known to the registry" is not enough. The `additional_roots` entry leaves `_PATH_LIKE_ALLOWLIST` in `tests/unit/test_error_boundary.py`. This is the live write risk and ships first. |
| `workspace-selection-authorized-roots` | No. A call selects only a workspace inside a sanctioned root. A server started for project A refuses a path in unrelated project B unless B is sanctioned. |
| `output-dir-anchorless-boundary` | Today's confinement to the call's own workspace stays (`resolve_workspace_dir`), and the sanctioned-root check is added on top. A relative `output_dir` that climbs out of the workspace stays refused; an absolute one inside the roots but outside the call's workspace is refused. An absolute `output_dir` with no workspace determinable is refused, with no fallback. This is not a loosening: the workspace is already inside a sanctioned root, so the added check can only refuse more. |
| `implicit-workspace-unlocked-window` | Order: (1) validate parameters, (2) check every path against the sanctioned roots, (3) only then select or create the workspace. Steps 1 and 2 have no side effects. The pure root resolution and the workspace containment check (ADR 0006) run before any backend starts; backend start, lease and selection come last. **Defect fixed (Piece C):** today `tool_error_boundary` runs `_resolve_backends`, which starts backends, takes a lease and marks the workspace selected, before `_validate_params` checks identifiers and containment, so a call that is then rejected has already started Pyright and selected a workspace. |

### Which error wins

Parameter validation (step 1) runs before the root check (step 2). A call with an invalid parameter and an unsanctioned path fails with `INVALID_INPUT` and no side effect. A call with valid parameters and an unsanctioned path fails with `SANCTIONED_ROOT`. Both leave the registry unchanged.

### The refusal

One typed error, `SanctionedRootError(ToolInputError)`, code `SANCTIONED_ROOT`, surfaced as `[SANCTIONED_ROOT] ...` like `AMBIGUOUS_WORKSPACE`. It is distinct from `INVALID_INPUT`. Messages are path-free (parameter label and list index only; no path value, no configured roots, no existence hint) and name the setting:

| Case | Message |
|---|---|
| No roots configured | `[SANCTIONED_ROOT] No sanctioned roots are configured, so every path is refused. Set PYTHON_REFACTOR_MCP_SANCTIONED_ROOTS (entries delimited by the OS path separator) and restart the server.` |
| Outside the roots | `[SANCTIONED_ROOT] The path in parameter <label> is outside the sanctioned roots. Add its root to PYTHON_REFACTOR_MCP_SANCTIONED_ROOTS and restart the server.` |

The two cases differ in text and are told apart by the opening sentence ("No sanctioned roots are configured" vs "outside the sanctioned roots"), which tests pin.

## Rulings (operator, 2026-11-18)

1. `output_dir` keeps its workspace confinement and gains the sanctioned-root check (an earlier draft widened it; confinement already existed).
2. A CLI `workspace_root` outside the roots, or empty roots, does not stop the server: no pre-warm, one stderr line, `server_status` reports the state, path calls are refused.
3. The marker walk stops at the sanctioned root, with a visible signal. Consequence: **which configuration applies can change for anyone who sanctions a subdirectory.** With sanctioned `D:\repo\pkg` and a `pyproject.toml` at `D:\repo`, the workspace is `D:\repo\pkg` and the parent configuration is not read. Sanction the project root if its configuration should apply.
4. Client roots: nothing is built.

## Tests (each red on current `main`)

| Piece | Test |
|---|---|
| A | `.` as the setting, server started from a directory outside the project: resolves against that directory. |
| A | A link inside a sanctioned root pointing outside it: refused. |
| A | Case-insensitive match on Windows; `D:\repo2` is not inside `D:\repo`; refusal identical for existing and missing paths. |
| A | The two messages differ, are path-free and name the setting. |
| B | `additional_roots` outside every sanctioned root with `apply=true`: refused, no `Project` opened, no file opened or written. |
| B | A changed path outside the roots at apply time: refused, nothing written. |
| C | Path in an unsanctioned project: refused, no backend started, registry unchanged. |
| C | No roots configured: every path call refused with the "not configured" message. |
| C | Roots empty at startup: no pre-warm, `server_status` reports `configured: false, count: 0`, first path call refused with the "not configured" message, one stderr line. |
| C | CLI `workspace_root` outside the roots: same shape with the "outside the roots" message. |
| C | Invalid parameters plus an unsanctioned path: `INVALID_INPUT` wins, no workspace side effect. |
| C | A client root outside the sanctioned roots grants nothing. |
| C | Sanctioned subdirectory with a `pyproject.toml` above it: workspace is the sanctioned root, the parent configuration is not read, `server_status` shows `root_source: sanctioned_root`. |
| D | Relative `output_dir` climbing out of the workspace: refused. |
| D | Absolute `output_dir` inside the roots but outside the call's workspace: refused. |
| D | Absolute `output_dir` with no workspace determinable: refused. |

## Migration (breaking; one `changed-breaking-*` fragment per shipped piece)

- Refused now: any path outside the sanctioned roots, every path while the setting is empty, and `multi_project_rename` roots outside them. A server registered once for many repositories (user scope) must have its roots configured, or every path call is refused.
- Configure: `PYTHON_REFACTOR_MCP_SANCTIONED_ROOTS` in the client's server `env`, for example `"."` for a repository-scoped registration or `D:\repos` for a user-scope one. Empty means denied.
- Client roots: users see no change; they were never read.
- Configuration can change: sanctioning a subdirectory of a project makes that subdirectory the workspace when no marker lies inside it, so a `pyproject.toml` or `pyrightconfig.json` above it is no longer read. Sanction the project root if its configuration should apply. `server_status` shows which case applies per workspace.
- Startup with a `workspace_root` argument outside the roots, or with empty roots: the server starts and prints one line on stderr; path calls are refused until the setting is fixed.
- Known limits: backend-internal reads are outside the boundary (see Scope); a link created between the check and the write is re-checked at apply only for the tools named above.

## Work order (each piece mergeable alone; dependency-chained rows are written on approval)

| Piece | Content | Closes |
|---|---|---|
| A | This ADR, the root set (`config.py`) and one shared path-check function, the `SANCTIONED_ROOT` error, tests; no tool consults it yet. | none |
| B | `multi_project_rename` write guard (answer 1), apply-time re-check, allow-list entry removed. | `multi-project-rename-roots` |
| C | Workspace selection (answer 2) and boundary reordering (answer 4), registry marker walk bounded, CLI `workspace_root` rule, example config in `docs/setup.md`. | `workspace-selection-authorized-roots`, `implicit-workspace-unlocked-window` |
| D | `output_dir` (answer 3). | `output-dir-anchorless-boundary` |

Piece B is taken first if anything is. Rows A, B, C, D are chained by `deps` (B on A, C on B, D on C); each piece is correct and mergeable alone.

## References

- Roslyn-Backed-MCP `docs/decisions/0002-configured-sanctioned-root-boundary.md`, `SECURITY.md`, `docs/setup.md`, `ai_docs/references/environment-variables.md`; its open row `sanctioned-root-refusal-names-no-remedy` (the lesson behind the message text above).
- ADR 0004 (refuse unless every occurrence is accounted for), ADR 0006, ADR 0011, ADR 0001 (contract-care).
