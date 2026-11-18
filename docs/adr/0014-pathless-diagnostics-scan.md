# ADR 0014 A path-less `get_diagnostics` scans the workspace and fails whole

Date 2026-11-18

Status Accepted

## Context

`get_diagnostics` with neither `file_path` nor `file_paths` was documented as "the full project" but returned the backend's push cache: the diagnostics Pyright had published for documents already open in the session. The client runs Pyright with `diagnosticMode: openFilesOnly`, so a fresh session published nothing and the call answered `[]` (a false "clean"). After files were opened by other calls it answered an arbitrary subset that depended on session history. The cache also had no failure channel and no notion of scope.

## Decision

- **Scope.** The path-less call enumerates the Python files under the selected workspace root (`python_files`, the same exclusions as `get_workspace_diagnostics`) and pulls each file's diagnostics with `textDocument/diagnostic` through one `get_diagnostics_many` batch (one resync of the already-open documents, then bounded concurrency). `root_path` only selects the workspace (ADR 0007, ADR 0012); `directory` stays on `get_workspace_diagnostics`. The walk is `os.walk` from the workspace root with the default directory exclusions: directory symlinks are not followed, and nested projects under the root are included (their files are part of the selected workspace tree, as for `get_workspace_diagnostics`); a nested project selected as its own workspace (ADR 0002) scans only its own tree.
- **Failure.** If any file's diagnostics cannot be read (timeout, unreadable file, backend error), the call raises `PyrightError` naming how many of how many files failed and the first three with their error types. It never returns a partial list, because a list has no failure channel and a partial list reads as clean. Cancellation propagates.
- **Open set.** The scan closes (`textDocument/didClose`) the documents it opened, so repeated path-less calls do not grow the language server's open set. Ownership is per document, tracked under the backend's document lock: a document that was already open is never closed; a document an ordinary request (or a scan that keeps documents open, such as `get_workspace_diagnostics`) uses meanwhile is adopted by that request and stays open; overlapping path-less scans share a document and the last one to end closes it. A scan therefore never closes a document another request or scan is using.
- **Push cache removed.** The `publishDiagnostics` handler and its cache are deleted; `PyrightLSPClient.get_diagnostics` takes a file path only (no `None`).
- **Signature.** `analysis.get_diagnostics` gains keyword-only `config`; the path-less form needs it.

## Rejected

- Keeping the push cache and documenting it: its content depends on which files other calls opened.
- A `scan_failures` field on the result: changes the return type of an existing tool for every caller; `get_workspace_diagnostics` already provides that shape.
- Returning the readable files and logging the rest: a partial list is indistinguishable from a clean one.

## Consequences

- One unreadable file, or one 5 s per-file timeout, fails the whole path-less call after the full scan ran. Use `get_workspace_diagnostics` (aggregated counts, failures listed in `scan_failures`) for a scan that tolerates them.
- Latency and payload grow from "whatever was cached" to the whole workspace; `limit`, `severity_filter` and `suppress_codes` apply after the scan.
- `find_unused_imports` and the other per-file callers are unchanged: they already convert a per-file failure into a `ScanFailure`.

## Migration

- A caller that relied on `get_diagnostics()` returning the cached subset now receives every diagnostic in the workspace (use `limit` or `severity_filter` to bound it) and may receive a `PyrightError`; handle it by retrying per file with `file_paths`, or switch to `get_workspace_diagnostics`.
- Python-internal: backend `get_diagnostics(None)` is removed; pass a path, or use `get_diagnostics_many`.
