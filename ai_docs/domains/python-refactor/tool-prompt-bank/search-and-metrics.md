# Tool Prompt Bank — Search, Metrics & Infrastructure
<!-- purpose: Goal / Validation / Chaining prompt triple per tool for the Search, Metrics & Infrastructure categories. -->

Format defined in `../mcp-checklist.md` §E. Tool contracts are canonical in `../reference.md`.
Index: `README.md`.

## Search

- `search_symbols`:
  - Goal: "Run `search_symbols` for `load_*` and return top 10 matches with kind + path."
  - Validation: "Run `search_symbols` with empty query and confirm the guard-clause rejection."
  - Chaining: "Use `search_symbols` to locate a candidate, then `goto_definition` to confirm identity."
- `project_search`:
  - Goal: "Run `project_search` for a literal string and return paths + line counts."
  - Validation: "Run `project_search` with a regex of unbalanced parens and show the regex-error envelope."
  - Chaining: "Use `project_search` to find a text occurrence, then `find_references` to widen into symbol scope."
- `structural_search`:
  - Goal: "Run `structural_search` for `except Exception: pass` and return each match location."
  - Validation: "Run `structural_search` with a malformed pattern and show the parse-error response."
  - Chaining: "Use `structural_search` matches as candidates for `apply_code_action` or `restructure`."
- `structural_replace`:
  - Goal: "Run `structural_replace` with a matcher pattern + `$name`-capture replacement template on one file, `apply=false`, and return the proposed edits."
  - Validation: "Run `structural_replace` with a replacement template referencing an undefined `$name` capture and show the validation error."
  - Chaining: "Use `structural_search` to confirm match sites, then `structural_replace` with the same pattern to rewrite them."
- `dead_code_detection`:
  - Goal: "Run `dead_code_detection` and return only unreferenced public functions."
  - Validation: "Run `dead_code_detection` on a package where every symbol is exported and confirm zero findings."
  - Chaining: "Feed `dead_code_detection` results into `find_references` to confirm zero sites before deleting."
- `unused_symbol_sweep`:
  - Goal: "Run `unused_symbol_sweep` on a package and return exported symbols with zero cross-file references."
  - Validation: "Run `unused_symbol_sweep` on a module whose export is registered via an `mcp`/`tool` decorator and confirm it is skipped."
  - Chaining: "Feed `unused_symbol_sweep` results into `find_references` to confirm zero sites, then propose deletion."
- `find_duplicated_code`:
  - Goal: "Run `find_duplicated_code` and return the top 3 clones by size."
  - Validation: "Run `find_duplicated_code` on a single-file project and confirm empty result."
  - Chaining: "Use `find_duplicated_code` hot spots as input to `extract_method` or `use_function`."
- `suggest_imports`:
  - Goal: "Run `suggest_imports` for an unresolved name and return ranked import candidates."
  - Validation: "Run `suggest_imports` on an already-imported name and confirm no-op response."
  - Chaining: "Use top-ranked `suggest_imports` result, then `organize_imports` to normalize placement."
- `find_unused_imports`:
  - Goal: "Run `find_unused_imports` on a file and return a per-line removal list."
  - Validation: "Run `find_unused_imports` on a file with only used imports and confirm empty output."
  - Chaining: "Use `find_unused_imports`, then `organize_imports` with `apply=true` to clean + sort in one pass."
- `autoimport_search`:
  - Goal: "Run `autoimport_search` for `Path` and return exact module:name candidates."
  - Validation: "Run `autoimport_search` on an empty query and show the input-validation error."
  - Chaining: "Pair `autoimport_search` with `suggest_imports` when multiple tool hits disagree."

## Metrics

- `code_metrics`:
  - Goal: "Run `code_metrics` on a file and return cyclomatic complexity per function, sorted desc."
  - Validation: "Run `code_metrics` on an empty file and confirm the zero-metrics envelope."
  - Chaining: "Rank hot spots with `code_metrics`, then `extract_method` on the top complexity offender."
- `get_coupling_metrics`:
  - Goal: "Run `get_coupling_metrics` on a package and return afferent/efferent counts per module."
  - Validation: "Run `get_coupling_metrics` on a single-file package and show the degenerate case."
  - Chaining: "Use `get_coupling_metrics` to find fan-in hot spots, then `find_references` for detail."
- `get_module_dependencies`:
  - Goal: "Run `get_module_dependencies` on a module and return only first-party imports."
  - Validation: "Run `get_module_dependencies` on a syntactically broken module and show the parse-error envelope."
  - Chaining: "Use `get_module_dependencies`, then `check_layer_violations` to flag illegal edges."
- `get_module_public_api`:
  - Goal: "Run `get_module_public_api` and return only names exported via `__all__` or re-exports."
  - Validation: "Run `get_module_public_api` on a private module and confirm empty-API response."
  - Chaining: "Use `get_module_public_api`, then `find_references` cross-repo to size breakage for a rename."

## Change history & previewing

- `diff_preview`:
  - Goal: "Run `diff_preview` on a pending TextEdit list and summarize top 3 hunks."
  - Validation: "Run `diff_preview` with an empty edit list and confirm the no-op response."
  - Chaining: "Pipe any refactor `apply=false` result into `diff_preview`; only apply if diff looks right."
- `refactor_transaction`:
  - Goal: "Run `refactor_transaction` with an ordered `(tool, args)` step list and return the per-step `applied`/`rolled_back`/`failed` status."
  - Validation: "Run `refactor_transaction` with two steps whose char spans overlap and show the overlap-abort + full rollback."
  - Chaining: "Preview each step individually, then compose them into one `refactor_transaction` call for atomic apply."
- `begin_change_stack`:
  - Goal: "Run `begin_change_stack` and return the new stack id."
  - Validation: "Run `begin_change_stack` when one is already open and show the nested-stack rejection."
  - Chaining: "Call `begin_change_stack`, perform refactors, then `commit_change_stack` or `rollback_change_stack`."
- `commit_change_stack`:
  - Goal: "Run `commit_change_stack` and return a summary of files changed."
  - Validation: "Run `commit_change_stack` with no open stack and show the invalid-state error."
  - Chaining: "After `commit_change_stack`, call `get_diagnostics` on the touched file set."
- `rollback_change_stack`:
  - Goal: "Run `rollback_change_stack` and confirm the workspace matches the pre-stack state."
  - Validation: "Run `rollback_change_stack` after a commit and show the already-committed rejection."
  - Chaining: "If a post-apply `get_diagnostics` shows regressions, call `rollback_change_stack` and try a different refactor."
- `undo_refactoring`:
  - Goal: "Run `undo_refactoring` and return the reverted change id + files restored."
  - Validation: "Run `undo_refactoring` with an empty history and show the no-history response."
  - Chaining: "Pair `undo_refactoring` with `get_refactoring_history` to pick the correct revert target."
- `redo_refactoring`:
  - Goal: "Run `redo_refactoring` and return the reapplied change id."
  - Validation: "Run `redo_refactoring` with nothing to redo and show the empty-redo response."
  - Chaining: "Use `undo_refactoring`, inspect diagnostics, then `redo_refactoring` if the revert was wrong."
- `get_refactoring_history`:
  - Goal: "Run `get_refactoring_history` and return the last 10 change entries with timestamp + tool."
  - Validation: "Run `get_refactoring_history` on a fresh session and confirm the empty list."
  - Chaining: "Use `get_refactoring_history` to audit recent edits, then `undo_refactoring` selectively."

## Infrastructure

- `list_environments`:
  - Goal: "Run `list_environments` and return the resolved interpreter path for the primary workspace."
  - Validation: "Run `list_environments` in an environment with no venv and confirm the fallback interpreter entry."
  - Chaining: "Use `list_environments` output to decide whether to call `create_type_stubs`."
- `server_status`:
  - Goal: "Run `server_status` and return the `degraded` flag plus per-workspace backend liveness."
  - Validation: "Run `server_status` with zero workspaces loaded and confirm it still returns a valid envelope."
  - Chaining: "Call `server_status` first when a tool call behaves unexpectedly, to rule out a Pyright-down fallback-to-Jedi condition."
- `restart_server`:
  - Goal: "Run `restart_server` and confirm the Pyright LSP lifecycle restarts cleanly."
  - Validation: "Run `restart_server` mid-refactor and show the queued-operation rejection."
  - Chaining: "After `restart_server`, call `get_workspace_diagnostics` to re-seed analysis state."
- `create_type_stubs`:
  - Goal: "Run `create_type_stubs` for a third-party package and return the generated `.pyi` path."
  - Validation: "Run `create_type_stubs` on a package already shipping stubs and confirm no-op."
  - Chaining: "Generate with `create_type_stubs`, then `get_type_coverage` to confirm improvement."
- `check_type_stub_freshness`:
  - Goal: "Compare a `.py` module with its adjacent `.pyi` stub and return callable signature drift."
  - Validation: "Confirm overload sets and Protocol classes appear as explicit conservative skips, not false-positive mismatches."
  - Chaining: "Run `check_type_stub_freshness`, then regenerate stale third-party stubs with `create_type_stubs` when applicable."
