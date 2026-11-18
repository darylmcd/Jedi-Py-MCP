# ADR 0011 Reject UNC and device-namespace paths before filesystem access

Date 2026-11-18

Status Accepted

## Context

On Windows a UNC path (`\\server\share\x.py`) is absolute, so it passed the absolute-path check and reached `Path.resolve()` and the marker probes (`.exists()`, `.is_dir()`) of workspace resolution before any containment check. Measured on Windows 11 with Python 3.14: `Path.resolve()` on a UNC, `\\?\UNC\...` or `\\.\...` path makes 3-4 `_getfinalpathname` calls, and a nonexistent loopback share (`\\127.0.0.1\nosuchshare\a\b.py`) took 2.2 s, an SMB connection attempt. A remote host receives that connection (and the NTLM negotiation SMB carries) from any caller-chosen path. The forward-slash spelling (`//server/share/x`) and the extended spellings (`\\?\UNC\server\share`, `\\?\Volume{...}`, `\\?\GLOBALROOT`, `\\.\pipe\x`) behave the same. `\\?\C:\x` is a local path: no network I/O, and an existing contract test requires it to resolve in scope.

## Decision

A caller-supplied path string is classified before it is resolved, and a UNC or device-namespace path is rejected with `[INVALID_INPUT]`.

- **Rule.** After `/` is read as `\`, a path that starts with two backslashes is rejected unless its drive part is a bare local drive in the extended-length form (`\\?\C:`). The check is pure string work (`util.shared.is_network_or_device_path`, `require_local_path`) and is host-conditional: with POSIX rules `//srv/share` is an ordinary path.
- **Where.** `tool_runtime._require_absolute` (every `PATH_PARAMS`, `file_paths`, nested `edits`/`symbols` and `refactor_transaction` step path, before the absolute check and before any resolution); `tool_runtime._reject_network_only_paths` (each `additional_roots` entry of `multi_project_rename`: classified only, no absolute or containment rule, which stays the open row `multi-project-rename-roots`); `RopeBackend._workspace_python_file` (the sink that guards `split_module` `source_file` and `target_modules` keys, which the boundary tables do not see); `validate_workspace_path` (so `output_dir` and direct callers); `__main__.main` and `server.run_server` for the positional `workspace_root`.
- **Startup.** A UNC `workspace_root` is refused at startup rather than pre-warmed: every later tool path would be rejected, so a server pre-warmed on a share could not be used. This is not an allow-list.
- **Guard, not sandbox.** The rule classifies the string the caller sent. A symlink or junction inside a workspace that targets a share, a mapped drive letter that points at a share, and a share reached through a subst or mount are out of scope. The related boundary gaps are tracked in the open row `output-dir-anchorless-boundary`. `util/python_detect.py` (~:53-60) reads an absolute poetry `venvPath` from the workspace `pyproject.toml` and `VIRTUAL_ENV`, then calls `is_dir()`/`exists()` on it; a UNC value there comes from workspace content or the environment, not from a caller-supplied tool string, so it is out of scope of this guard and tracked as a follow-up row.

## Migration

UNC and device-namespace paths, and a UNC `workspace_root`, are rejected with `[INVALID_INPUT]` (startup: exit message). Map the share to a drive letter (`net use Z: \\server\share`) and pass `Z:\...`, or use the local `\\?\C:\...` spelling. POSIX hosts are unaffected.
