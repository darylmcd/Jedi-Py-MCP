# 02 — C1 Tool surface (live calls)

Evidence: `raw/c1_calls.json` (1655 call records: args, outcome, client-visible text, structuredContent, seconds, workspace-diff), `raw/perf_calls.json` (repo-scale timing), harness in `harness/`.

## Method

| Step | Detail |
|---|---|
| Valid call | Hand-built args per tool against `<scratch>/ws` (see `harness/c1.py.txt::valid_args`). Refactoring tools always preview (`apply` absent). |
| Idempotency (RO tools) | Valid call repeated; `structuredContent` compared for equality. |
| Missing-required | `{}` and "valid minus first required". |
| Null / wrong-type | first required → `null`; first int→`"abc"`, str→`12345`, list→`"not-a-list"`, bool→`"maybe"`, object→`[1,2]` (`apply` never mutated). |
| Unknown arg | valid + `__unknown_extra__: 1`. |
| Edge | ints `-1` / `10**9` (line, character, limit, offset, depth, index, …); strings empty / whitespace / unicode / 5000-char / punctuation; paths empty / nonexistent / relative / dir / unicode-nonexistent / outside-workspace / 5000-char; lists empty / 60-deep nesting. |
| Side-effect guard | SHA-1 of every workspace file before/after each call; any drift = finding, then restore. |
| Output check | `ClientSession.validate_tool_result` validates every non-error `structuredContent` against the advertised `outputSchema`. |
| Stateful tools | ordered sequence: history → undo/redo on empty history → commit/rollback without begin → begin → begin twice → preview inside stack → rollback ×2 → begin → commit empty → `refactor_transaction` input-error contracts → `restart_server` → post-restart `server_status` / `get_type_info` → profile gating → unknown tool. |
| Timing | every call timed; repo-scale pass on a 137-file copy of this repo (`harness/perf.py.txt`). |

## Aggregate results

| Metric | Value |
|---|---|
| Calls | 1655 (383 ok / 1272 `isError:true`) |
| Crashes / transport deaths / timeouts | **0** |
| JSON-RPC protocol errors | **0** (all failures surfaced as `isError` tool results — correct per spec) |
| outputSchema violations | **0** |
| Tracebacks leaked to client | **0** |
| Preview calls that wrote to disk | **0** (workspace byte-identical to pristine at end) |
| RO tools non-idempotent | **0** |
| Profile gating | refactoring-profile call to `call_hierarchy` → `Unknown tool: call_hierarchy` (correct) |
| Error-text taxonomy | 430 pydantic validation (clear), 332 `[WORKSPACE_RESOLUTION]` (clear enough), **111 opaque `Error executing tool X`**, **397 `[*_BACKEND]` generic "backend failed … retry"** |
| Calls > 30 s (fixture) | 0 — max 1.27 s (`restart_server`) |
| Calls > 30 s (repo copy) | **2** — `dead_code_detection` 30.39 s, `unused_symbol_sweep` 39.72 s |

## Findings (C1)

| ID | Sev | Finding | Call capture | Anchor |
|---|---|---|---|---|
| mcp-surface-opaque-input-errors | high | Any non-`BackendError` exception (`ValueError` from identifier/path/limit validation, `FileNotFoundError`, …) escapes `tool_error_boundary`; the SDK replaces it with the bare string `Error executing tool <name>` — the reason is dropped. 111 calls / 33 tools, incl. two **valid** calls. Server stderr logs each as "raised an unexpected exception" with a full traceback. | `rename_symbol{new_name:"   "}` → `Error executing tool rename_symbol` (stderr: `ValueError: '   ' is not a valid Python identifier (parameter: new_name)`); `check_type_stub_freshness{source_file:<ws>/src/audit.py}` → opaque (stderr: `FileNotFoundError: Stub file does not exist: …audit.pyi`); `apply_code_action` valid → opaque (stderr: `ValueError: No code actions were available for the requested location.` — description promises "omit action_title to list available actions"); `find_references{limit:-1}` → opaque (`apply_limit` `ValueError`) | `src/python_refactor_mcp/tool_runtime.py:259`, `util/shared.py:106`, `util/shared.py:33`, `tools/refactoring/code_actions.py:24`, `tools/analysis/type_stubs.py:158` |
| mcp-surface-input-errors-as-backend-failures | high | Caller-input errors are reported as backend outages with retry advice. Negative / out-of-range `line`/`character` (37 positional tools × 4 variants), nonexistent file / directory path (~70 path-taking tools), `refactor_transaction` documented INPUT errors, undo/redo on empty history, commit/rollback without `begin`, `begin` twice, unsupported `generate_code` kind → `[PYRIGHT_BACKEND] Type-analysis backend failed; check server_status and retry.` / `[ROPE_BACKEND] … inspect server diagnostics before retrying.` **Regression:** the 2026-06-19 audit (`ai_docs/audits/20260619-2130/02_mcp_tools.md`) observed `File not found: …`; blanket redaction arrived in `e93207e` (#93). | `get_type_info{line:-1}` → `[PYRIGHT_BACKEND] Type-analysis backend failed; check server_status and retry. Failure ID: b04dd61739c5.`; `get_type_info{file_path:<ws>/src/does_not_exist.py}` → same; `refactor_transaction{steps:[]}` → `[ROPE_BACKEND] Refactoring backend failed; inspect server diagnostics before retrying.`; `undo_refactoring{}` (empty history) → same | `src/python_refactor_mcp/errors.py:14-38`, `tool_runtime.py:216-234`, `backends/pyright_lsp.py:527-545` (out-of-range deliberately raises `PyrightError`), `backends/_threading.py:47` |
| mcp-surface-prepare-rename-always-null | high | `prepare_rename` returns `null` ("not renameable") for a renameable symbol. Pyright answers with a bare `Range` `{start,end}`; the parser treats "dict without a `range` key" as `defaultBehavior` and returns `None`. The documented workflow ("use prepare_rename before rename_symbol") therefore always says no. | `prepare_rename{models.py, line:12, character:6}` (`class User`) → `{"result": null}`; same position `rename_symbol{new_name:"Member"}` → 4-file edit set. Raw LSP: `textDocument/prepareRename` → `{"result":{"start":{"line":12,"character":6},"end":{"line":12,"character":10}}}` | `src/python_refactor_mcp/backends/pyright_lsp.py:1190-1191`; weak test `tests/integration/test_end_to_end.py:348` (`payload is None or …`) |
| mcp-surface-unsupported-lsp-silently-empty | high | `selection_range`, `get_inlay_hints`, `get_semantic_tokens` always return `[]`: Pyright 1.1.411 answers `-32601 Unhandled method` for `textDocument/selectionRange`, `/inlayHint`, `/semanticTokens/full`, and the backend maps "unhandled" to an empty list. `apply_type_annotations` is built on inlay hints, so it always reports "No inferable type annotations found" (fixture has an unannotated `def untyped(p, q)`). Four advertised tools are non-functional and indistinguishable from "nothing here". | `selection_range{positions:[{line:19,character:8}]}` → `{"result": []}`; `get_inlay_hints{audit.py}` → `[]`; `get_semantic_tokens{audit.py, limit:20}` → `[]`; `apply_type_annotations{audit.py}` → `edits:0 "No inferable type annotations found"`. Raw LSP (`harness/lsp_probe.py.txt`): `{"error":{"code":-32601,"message":"Unhandled method textDocument/selectionRange"}}` (same for inlayHint, semanticTokens/full) | `backends/pyright_lsp.py:1023-1024`, `:1245-1246`, `:1304-1305`; tests assert only `isinstance(list)`: `tests/integration/test_end_to_end.py:424-429`, `:514-515` |
| mcp-surface-generate-code-broken | high | `generate_code` fails for **every** `kind`: the generator table references `rope.contrib.generate.create_class/create_function/create_variable`, which do not exist in rope 1.14 (API: `create_generate(kind, project, resource, offset)`); the `AttributeError` fires while building the dict, so `module`/`package` fail too (and their real signatures `create_module(project, name, sourcefolder)` don't match the `(project, resource, offset)` call). The `# pyright: ignore[reportAttributeAccessIssue]` comments suppress exactly this error. | `generate_code{audit.py, line:109, character:11, kind:"function"}` → `[ROPE_BACKEND] Refactoring backend failed…`; direct backend probe (`harness/gen_probe.py.txt`): `AttributeError: module 'rope.contrib.generate' has no attribute 'create_class'` | `src/python_refactor_mcp/backends/rope_backend.py:997-1007` |
| mcp-surface-create-type-stubs-false-success | high | `create_type_stubs` returns `true` without generating anything. It forwards `[package_name, output_dir]` to `pyright.createtypestub` and returns `True` whenever the response has no JSON-RPC error; Pyright answers `result:null` for every argument shape tried and writes neither `typings/` nor `output_dir`. Garbage package names also return `true`. Tool has no preview mode and is not flagged as writing. | `create_type_stubs{package_name:"parso", output_dir:<scratch>/stubs_out}` → `{"result": true}`, `stubs_out` never created; `{package_name:"not an identifier!!"}` → `{"result": true}`; raw `pyright.createtypestub` with `["parso"]`, `[<ws uri>,"parso"]`, `[<ws path>,"parso"]` → `result:null`, no `typings/` | `backends/pyright_lsp.py:1389-1410`, `tools/analysis/type_stubs.py:20-26` |
| mcp-surface-failure-id-dead-end | medium | Every backend error tells the caller to "inspect server diagnostics" by Failure ID, but the server installs no log formatter/handler; the `extra={exception_types, traceback_locations}` payload is never rendered. stderr shows only `Backend failure id=<id> tool=<t> code=<c>` — the `generate_code` root cause above was recoverable only by calling the backend directly. | 729 `Backend failure id=…` lines in the run's stderr, none carrying exception type/location | `tool_runtime.py:220-233`; no `basicConfig`/`dictConfig`/`Formatter` anywhere under `src/` |
| mcp-surface-sweep-tools-slow | medium | Repo-scale runtime > 30 s on a 137-file workspace. | `dead_code_detection{root_path:<ws_repo>}` 30.39 s / 166 KB; `unused_symbol_sweep{root_path:<ws_repo>/src/python_refactor_mcp}` 39.72 s / 75 KB | `tool_registry.py:1224`, `:1257` (per-symbol reference lookups) |
| mcp-surface-unbounded-payloads | medium | Default caps don't bound response size. `get_symbol_outline` workspace scan applies `limit=500` to top-level items only → 500 roots / 9,933 nodes / **7.5 MB** text. No default limit on `get_module_dependencies` (652 KB), `code_metrics` (339 KB), `dead_code_detection` (166 KB), `search_symbols` (125 KB), `find_type_users` (118 KB). | `get_symbol_outline{root_path:<ws_repo>/src/python_refactor_mcp}` → 7,527,317 chars | `server.py:170-174` |
| mcp-surface-default-inliner-overpromise | medium | `argument_default_inliner` inlines the default into callers but leaves the default in the signature, contradicting "then remove the default from the signature". Negative `index` is accepted and Python-indexed (`-1` → last param). | `argument_default_inliner{helper, index:1}` → new text still contains `def helper(a: int, b: int = 2) -> int:`; `index:-1` → ok, same edit | `server.py:210-221` (rope `ArgumentDefaultInliner.remove` defaults False) |
| mcp-surface-preview-drops-file-ops | medium | `RefactorResult` carries only `TextEdit`s, so file creations/moves are invisible in preview: `move_module` preview = 0 edits + "Moved module …"; `module_to_package` preview = one identity replace of `utils.py` + "Converted module to package". A reviewer cannot see what `apply=True` will do on disk. | `move_module{utils.py → src/sub}` → `edits:[]`; `module_to_package{utils.py}` → edit whose `new_text` equals the current file | `models.py:273-281`, `backends/rope_backend.py:834-842`, `:960-975` |
| mcp-surface-missing-root-silently-clean | medium | Nonexistent scope inputs yield "clean" results with no failure signal: `dead_code_detection` / `unused_symbol_sweep` with nonexistent `root_path` → `items:[]`, `scan_failures:[]`; `get_symbol_outline` nonexistent `file_path` → `[]`; `get_type_coverage` nonexistent file → `return_coverage_pct:100.0` (scan_failure present, headline misleads). Contrast: `code_metrics`, `security_scan`, `find_unused_imports`, `structural_search` correctly return `scan_failures:[{error_type:"FileNotFoundError"}]`. | `dead_code_detection{root_path:<ws>/src/does_not_exist.py}` → `{"items":[],"total_count":0,"scan_failures":[]}` | `tools/search/_helpers.py:122` (`resolve_target_files`), `server.py:158-190` |
| mcp-surface-numeric-bounds-inconsistent | low | Same parameter, different contracts: `limit:-1` raises (opaque) in 9 tools but is silently ignored in `dead_code_detection`, `unused_symbol_sweep`, `get_workspace_diagnostics`, `get_semantic_tokens`; `offset:-1` echoed back; `depth:-1` opaque while `depth:10**9` accepted; `undo_refactoring{count:-1}` → `"Undid -1 operation(s)", applied:true`; `max_items:-1` accepted. Top-level `line`/`character` schemas lack `minimum: 0` (only `$defs.Position` has it). | `undo_refactoring{count:-1}` → `{"description":"Undid -1 operation(s)","applied":true}` | `util/shared.py:24-36`, `tool_registry.py:1517` |
| mcp-surface-unknown-args-ignored | low | 98 of 101 parameterized tools accept and silently drop unknown keys (no `additionalProperties:false`); a typo in an optional param (`include_contxt`, `aply`) silently falls back to the default. | `call_hierarchy{…, __unknown_extra__:1}` → ok | SDK-generated arg models (all tool schemas) |

## Stateful sequence (observed)

| Step | Result | Verdict |
|---|---|---|
| `undo_refactoring` / `redo_refactoring` on empty history | `[ROPE_BACKEND] …` | error ok; message generic (see input-errors-as-backend-failures) |
| `commit_change_stack` / `rollback_change_stack` without begin; `begin_change_stack` twice | `[ROPE_BACKEND] …` | same |
| begin → `rename_symbol` preview inside stack → rollback | preview ok, `Change stack rolled back`, disk unchanged | correct |
| begin → commit empty | `applied:true`, 0 edits | correct |
| `refactor_transaction` empty / malformed / unsupported tool / missing `file_path` / `apply` inside args + bad tool | all rejected before any write (disk unchanged) | contract honored; messages generic |
| `restart_server` → `server_status` → `get_type_info` | restarted in 1.27 s, `degraded:false`, correct type after restart | correct |

## Per-tool matrix (generated by `harness/gen_tables.py.txt`)

| Tool | Valid call | Calls | Clear errors | Opaque errors | `*_BACKEND` on bad input | Edge inputs accepted | Unknown arg ignored | Idempotent (RO) | Max s | Disk writes in preview |
|---|---|---|---|---|---|---|---|---|---|---|
| `apply_code_action` | error_result (0.666s) | 18 | 9 | 6 | 3 | 0 | no | — | 0.67 | 0 |
| `apply_lint_fixes` | ok (0.386s) | 14 | 9 | 0 | 3 | 0 | yes | — | 0.39 | 0 |
| `apply_type_annotations` | ok (0.009s) | 13 | 8 | 0 | 3 | 0 | yes | — | 0.01 | 0 |
| `argument_default_inliner` | ok (0.069s) | 19 | 9 | 0 | 7 | 1 | yes | — | 0.07 | 0 |
| `argument_normalizer` | ok (0.054s) | 18 | 9 | 0 | 7 | 0 | yes | — | 0.05 | 0 |
| `autoimport_search` | ok (0.006s) | 11 | 3 | 0 | 0 | 5 | yes | yes | 0.01 | 0 |
| `begin_change_stack` | error-path only | 3 | 0 | 0 | 1 | 0 | no | — | 0.00 | 0 |
| `call_hierarchy` | ok (0.75s) | 23 | 10 | 1 | 7 | 2 | yes | yes | 0.75 | 0 |
| `change_signature` | ok (0.047s) | 21 | 11 | 0 | 7 | 1 | yes | — | 0.05 | 0 |
| `check_layer_violations` | ok (0.014s) | 8 | 4 | 0 | 0 | 1 | yes | yes | 0.01 | 0 |
| `check_type_stub_freshness` | error_result (0.008s) | 12 | 7 | 5 | 0 | 0 | no | — | 0.01 | 0 |
| `code_metrics` | ok (0.01s) | 14 | 8 | 0 | 0 | 3 | yes | yes | 0.01 | 0 |
| `commit_change_stack` | error-path only | 2 | 0 | 0 | 1 | 0 | no | — | 0.01 | 0 |
| `convert_function_to_method` | ok (0.418s) | 18 | 8 | 4 | 4 | 0 | yes | — | 0.42 | 0 |
| `convert_method_to_function` | ok (0.052s) | 18 | 8 | 4 | 4 | 0 | yes | — | 0.05 | 0 |
| `convert_to_dataclass` | ok (0.04s) | 18 | 8 | 4 | 4 | 0 | yes | — | 0.04 | 0 |
| `convert_to_pydantic` | ok (0.064s) | 18 | 8 | 4 | 4 | 0 | yes | — | 0.06 | 0 |
| `convert_to_typeddict` | ok (0.041s) | 18 | 8 | 4 | 4 | 0 | yes | — | 0.04 | 0 |
| `create_type_stubs` | ok (0.636s) | 17 | 3 | 0 | 0 | 12 | yes | — | 0.64 | 0 |
| `dead_code_detection` | ok (0.07s) | 18 | 8 | 0 | 0 | 7 | yes | yes | 0.07 | 0 |
| `deep_type_inference` | ok (0.699s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.70 | 0 |
| `diff_preview` | ok (0.004s) | 8 | 4 | 0 | 0 | 1 | yes | yes | 0.00 | 0 |
| `docstring_sync` | ok (0.025s) | 18 | 9 | 0 | 7 | 0 | yes | — | 0.03 | 0 |
| `encapsulate_field` | ok (0.014s) | 18 | 9 | 0 | 7 | 0 | yes | — | 0.01 | 0 |
| `expand_star_imports` | ok (0.047s) | 12 | 7 | 0 | 3 | 0 | yes | — | 0.05 | 0 |
| `extract_class` | ok (0.023s) | 21 | 10 | 4 | 5 | 0 | yes | — | 0.02 | 0 |
| `extract_method` | ok (0.02s) | 23 | 10 | 4 | 6 | 1 | yes | — | 0.02 | 0 |
| `extract_protocol` | ok (0.013s) | 22 | 10 | 7 | 0 | 2 | yes | yes | 0.01 | 0 |
| `extract_superclass` | ok (0.021s) | 21 | 10 | 4 | 5 | 0 | yes | — | 0.02 | 0 |
| `extract_variable` | ok (0.016s) | 22 | 9 | 4 | 6 | 1 | yes | — | 0.02 | 0 |
| `find_constructors` | ok (0.021s) | 14 | 4 | 5 | 0 | 2 | yes | yes | 0.02 | 0 |
| `find_duplicated_code` | ok (0.01s) | 16 | 9 | 0 | 0 | 4 | yes | yes | 0.01 | 0 |
| `find_errors_static` | ok (0.239s) | 13 | 7 | 0 | 2 | 1 | yes | yes | 0.24 | 0 |
| `find_implementations` | ok (0.006s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `find_references` | ok (0.029s) | 22 | 10 | 1 | 7 | 1 | yes | yes | 0.03 | 0 |
| `find_type_users` | ok (0.034s) | 23 | 11 | 1 | 7 | 1 | yes | yes | 0.03 | 0 |
| `find_unused_imports` | ok (0.009s) | 12 | 6 | 0 | 0 | 3 | yes | yes | 0.01 | 0 |
| `fix_circular_imports` | ok (0.018s) | 4 | 2 | 0 | 0 | 0 | yes | — | 0.02 | 0 |
| `fix_module_names` | ok (0.018s) | 2 | 0 | 0 | 0 | 0 | yes | — | 0.02 | 0 |
| `format_code` | ok (0.027s) | 13 | 8 | 0 | 3 | 0 | yes | — | 0.03 | 0 |
| `froms_to_imports` | ok (0.043s) | 12 | 7 | 0 | 3 | 0 | yes | — | 0.04 | 0 |
| `generate_code` | error_result (0.014s) | 23 | 9 | 0 | 14 | 0 | no | — | 0.02 | 0 |
| `get_all_names` | ok (0.061s) | 14 | 8 | 0 | 3 | 0 | yes | yes | 0.06 | 0 |
| `get_completions` | ok (0.016s) | 22 | 10 | 1 | 7 | 1 | yes | yes | 0.02 | 0 |
| `get_context` | ok (0.007s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `get_coupling_metrics` | ok (0.019s) | 4 | 1 | 0 | 0 | 0 | yes | yes | 0.02 | 0 |
| `get_declaration` | ok (0.008s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `get_diagnostics` | ok (0.008s) | 15 | 7 | 1 | 3 | 1 | yes | yes | 0.01 | 0 |
| `get_document_highlights` | ok (0.007s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `get_documentation` | ok (0.014s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `get_folding_ranges` | ok (0.008s) | 13 | 7 | 0 | 3 | 0 | yes | yes | 0.01 | 0 |
| `get_inlay_hints` | ok (0.006s) | 17 | 8 | 0 | 3 | 3 | yes | yes | 0.01 | 0 |
| `get_keyword_help` | ok (0.008s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `get_module_dependencies` | ok (0.019s) | 5 | 2 | 0 | 0 | 0 | yes | yes | 0.02 | 0 |
| `get_module_public_api` | ok (0.017s) | 13 | 7 | 3 | 0 | 0 | yes | yes | 0.02 | 0 |
| `get_refactoring_history` | ok (0.004s) | 4 | 0 | 0 | 0 | 0 | yes | yes | 0.01 | 0 |
| `get_semantic_tokens` | ok (0.006s) | 16 | 8 | 0 | 3 | 2 | yes | yes | 0.01 | 0 |
| `get_signature_help` | ok (0.01s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `get_sub_definitions` | ok (0.008s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `get_symbol_outline` | ok (0.025s) | 17 | 7 | 1 | 0 | 6 | yes | yes | 0.03 | 0 |
| `get_syntax_errors` | ok (0.008s) | 13 | 7 | 0 | 3 | 0 | yes | yes | 0.01 | 0 |
| `get_test_coverage_map` | ok (0.015s) | 12 | 6 | 0 | 0 | 3 | yes | yes | 0.01 | 0 |
| `get_type_coverage` | ok (0.009s) | 14 | 8 | 0 | 0 | 3 | yes | yes | 0.01 | 0 |
| `get_type_definition` | ok (0.007s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `get_type_hint_string` | ok (0.009s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `get_type_info` | ok (0.005s) | 20 | 9 | 0 | 7 | 0 | yes | yes | 0.08 | 0 |
| `get_workspace_diagnostics` | ok (0.019s) | 10 | 3 | 0 | 0 | 4 | yes | yes | 0.02 | 0 |
| `goto_definition` | ok (0.006s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `handle_long_imports` | ok (0.02s) | 12 | 7 | 0 | 3 | 0 | yes | — | 0.02 | 0 |
| `inline_method` | ok (0.186s) | 18 | 9 | 0 | 7 | 0 | yes | — | 0.19 | 0 |
| `inline_parameter` | ok (0.032s) | 18 | 9 | 0 | 7 | 0 | yes | — | 0.03 | 0 |
| `inline_variable` | ok (0.177s) | 18 | 9 | 0 | 7 | 0 | yes | — | 0.18 | 0 |
| `interface_conformance` | ok (0.006s) | 17 | 10 | 3 | 0 | 1 | yes | yes | 0.01 | 0 |
| `introduce_factory` | ok (0.03s) | 19 | 10 | 0 | 7 | 0 | yes | — | 0.03 | 0 |
| `introduce_parameter` | ok (0.024s) | 23 | 9 | 4 | 7 | 1 | yes | — | 0.02 | 0 |
| `list_environments` | ok (0.471s) | 3 | 0 | 0 | 0 | 0 | yes | yes | 0.47 | 0 |
| `local_to_field` | ok (0.034s) | 18 | 9 | 0 | 7 | 0 | yes | — | 0.03 | 0 |
| `method_object` | ok (0.022s) | 18 | 9 | 0 | 7 | 0 | yes | — | 0.02 | 0 |
| `module_to_package` | ok (0.035s) | 12 | 7 | 0 | 3 | 0 | yes | — | 0.04 | 0 |
| `move_method` | ok (0.026s) | 23 | 9 | 4 | 8 | 0 | yes | — | 0.03 | 0 |
| `move_module` | ok (0.037s) | 20 | 8 | 4 | 4 | 2 | yes | — | 0.04 | 0 |
| `move_symbol` | ok (0.09s) | 18 | 8 | 4 | 4 | 0 | yes | — | 0.12 | 0 |
| `multi_project_rename` | ok (0.043s) | 26 | 11 | 4 | 7 | 2 | yes | — | 0.04 | 0 |
| `no_such_tool` | error-path only | 1 | 1 | 0 | 0 | 0 | no | — | 0.00 | 0 |
| `organize_imports` | ok (0.011s) | 13 | 8 | 0 | 3 | 0 | yes | — | 0.01 | 0 |
| `prepare_rename` | ok (0.006s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `project_search` | ok (0.017s) | 12 | 4 | 0 | 0 | 5 | yes | yes | 0.02 | 0 |
| `redo_refactoring` | error-path only | 1 | 0 | 0 | 1 | 0 | no | — | 0.00 | 0 |
| `refactor_transaction` | error-path only | 8 | 3 | 0 | 5 | 0 | no | — | 0.00 | 0 |
| `relatives_to_absolutes` | ok (0.021s) | 12 | 7 | 0 | 3 | 0 | yes | — | 0.02 | 0 |
| `rename_symbol` | ok (0.041s) | 25 | 10 | 4 | 7 | 1 | yes | — | 0.46 | 0 |
| `restart_server` | ok (1.268s) | 1 | 0 | 0 | 0 | 0 | no | — | 1.27 | 0 |
| `restructure` | ok (0.021s) | 18 | 6 | 0 | 4 | 6 | yes | — | 0.02 | 0 |
| `rollback_change_stack` | error-path only | 3 | 0 | 0 | 2 | 0 | no | — | 0.00 | 0 |
| `search_symbols` | ok (0.087s) | 14 | 4 | 1 | 0 | 6 | yes | yes | 0.09 | 0 |
| `security_autofix` | ok (0.019s) | 11 | 6 | 0 | 3 | 0 | yes | — | 0.02 | 0 |
| `security_scan` | ok (0.008s) | 12 | 6 | 0 | 0 | 3 | yes | yes | 0.01 | 0 |
| `selection_range` | ok (0.005s) | 17 | 10 | 1 | 3 | 0 | yes | yes | 0.01 | 0 |
| `server_status` | ok (0.005s) | 4 | 0 | 0 | 0 | 0 | yes | yes | 0.01 | 0 |
| `simulate_execution` | ok (0.008s) | 19 | 9 | 0 | 7 | 0 | yes | yes | 0.01 | 0 |
| `split_module` | ok (0.538s) | 14 | 9 | 0 | 3 | 0 | yes | — | 0.81 | 0 |
| `structural_replace` | ok (0.025s) | 17 | 5 | 6 | 3 | 1 | yes | — | 0.05 | 0 |
| `structural_search` | ok (0.025s) | 21 | 8 | 6 | 0 | 4 | yes | yes | 0.03 | 0 |
| `suggest_imports` | ok (0.014s) | 19 | 8 | 0 | 3 | 5 | yes | yes | 0.01 | 0 |
| `test_impact_select` | ok (0.011s) | 12 | 5 | 1 | 0 | 3 | yes | yes | 0.01 | 0 |
| `type_hierarchy` | ok (0.01s) | 22 | 9 | 1 | 7 | 2 | yes | yes | 0.01 | 0 |
| `undo_refactoring` | error-path only | 4 | 1 | 0 | 1 | 0 | no | — | 0.02 | 0 |
| `unused_symbol_sweep` | ok (0.041s) | 18 | 8 | 0 | 0 | 7 | yes | yes | 0.04 | 0 |
| `use_function` | ok (0.031s) | 18 | 9 | 0 | 7 | 0 | yes | — | 0.03 | 0 |
