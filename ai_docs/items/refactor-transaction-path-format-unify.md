# refactor-transaction-path-format-unify — unify path formatting in refactor_transaction result

**row:** `refactor-transaction-path-format-unify` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tools/composite.py` (`_collect_target_files` / result assembly — uses `Path(file_path).resolve()`).
- `src/python_refactor_mcp/backends/rope_backend.py` (`_changed_char_spans` / `apply_transaction` `step_meta` — uses `_absolute_path(workspace_root / resource.path)`).

## Acceptance

- [ ] `TransactionResult.files_affected` entries are string-identical to the corresponding `diffs[].file_path` entries on Windows and POSIX (route both producers through one path helper, e.g. the backend's `_absolute_path`).
- [ ] Regression test asserts the two field families match for a multi-file transaction.

## Evidence

- `cand-refactor-transaction` (#70) code-quality review (2026-06-20): the composite assembles `files_affected` via `Path(...).resolve()` while the backend produces `diffs` paths via `_absolute_path`; the two can differ in case/separator for the same file on Windows, making the result fields inconsistent for the same edit.

## Context

- Cosmetic consistency fix; no behavior change to the transaction itself. Likely a 1-file change (composite reuses the backend's normalization).
