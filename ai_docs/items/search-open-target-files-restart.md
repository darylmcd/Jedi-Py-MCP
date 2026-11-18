# search-open-target-files-restart — Restart-safe multi-file open set

**row:** `search-open-target-files-restart` · **pri:** `Low` · **size:** `M` · **verified:** `93cd1b324525daf60c5666c8f1107db9ce846b21`

## Anchors

- `src/python_refactor_mcp/tools/search/_helpers.py:172-195`
- `src/python_refactor_mcp/backends/pyright_lsp.py:446-452`
- `src/python_refactor_mcp/backends/pyright_lsp.py:582-600`

## Acceptance

- [ ] After a Pyright restart mid-scan, every file in the `open_target_files` set is open again on the replacement session (not only the file of the in-flight `_document_request`), so a references scan stays independent of session history.
- [ ] `ensure_file_open` has explicit documented semantics: either it re-syncs edited on-disk content (like `_refresh_document`) or its docstring and the `PyrightSearchBackend` protocol state it only dedups; tests pin the chosen behaviour for an edited file.
- [ ] A test restarts the backend between `open_target_files` and the references phase and asserts the cross-file results match a no-restart run.

## Evidence

- `open_target_files` opens the set via `ensure_file_open`, which only opens when the path is absent from `_file_contents`; the `_document_request` replay (PR #203) reopens only the queried file on a replacement session, so the rest of the set is lost on restart.

## Context

- Follow-up from PR #203 (`pyright-restart-document-replay`).
