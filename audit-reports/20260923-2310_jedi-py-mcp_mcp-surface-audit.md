# MCP Surface Audit — Jedi-Py-MCP (`python-refactor` / `python-analysis`)

| Field | Value |
|---|---|
| Server id | `python-refactor` (refactoring profile, 75 tools) + `python-analysis` (analysis profile, 56 tools) — 108 unique |
| Version | 0.5.0 (`serverInfo`, `pyproject.toml`, `manifest.json` agree) @ `0f3f231` |
| Stack | Python 3.14, `mcp` 2.1.1 `MCPServer`; backends Pyright 1.1.411 LSP, Jedi, rope 1.14 |
| Transport | stdio, raw JSON-RPC client (`mcp.client.stdio` + `ClientSession`); host fast path deliberately not used |
| Mode | `--mode=full`, `--output-mode=findings` |
| Run | 2026-09-23 23:10 local; 1655 fixture calls + 22 repo-scale timing calls + raw Pyright/rope probes |
| Artifacts | `ai_docs/audits/20260923-2310/` → `_surfaces.md`, `01_inventory_mcp.md` … `07_mcp_parity.md`, `raw/` (full call captures), `harness/` (reproducer, `.py.txt` so lint ignores it) |
| Path placeholders | `<repo>` = this checkout, `<scratch>` = the disposable audit workspace, `<home>` / `<local-path>` = redacted local profile paths; substitute `<repo>`/`<scratch>` in `harness/harness_common.py.txt` to re-run |
| Safety | All calls ran against disposable scratch copies; no call wrote to the repo; 0 preview calls wrote to disk (hash-verified per call) |

## Verdict

The protocol layer is solid: 0 crashes, 0 timeouts, 0 JSON-RPC errors, 0 outputSchema violations, 0 tracebacks leaked, 0 disk writes from any preview, every read-only tool idempotent, required fields and types enforced on 100% of probes, profile gating correct. The defects sit one layer down:

1. **Error contract (2 rows).** 111 calls return a reasonless `Error executing tool X`. 396 caller-input mistakes, such as bad positions, missing files, empty transaction steps or undo with no history, come back as `[*_BACKEND] … retry` backend outages. That second one is a regression since the 2026-06-19 audit, caused by `e93207e`.
2. **Six advertised tools don't work, but look like they succeed or return clean-empty.**
   - `prepare_rename`: always `null`.
   - `selection_range`, `get_inlay_hints`, `get_semantic_tokens`: always `[]`.
   - `apply_type_annotations`: never finds anything.
   - `generate_code`: always fails.
   - `create_type_stubs`: returns `true` but writes nothing.

   For the first four, the integration tests accept `None` or an empty list, so CI stays green.
3. Observability, scale and copy gaps: Failure IDs can't be traced to anything, two sweeps take more than 30s, one response reached 7.5 MB, the layer check gives false-clean results, the manifest is invalid, and descriptions reference tools the active profile doesn't advertise.

## Findings

| # | ID | Sev | Check | One-line | Anchor |
|---|---|---|---|---|---|
| 1 | mcp-surface-opaque-input-errors | high | C1 | Non-`BackendError` exceptions (ValueError/FileNotFoundError) escape the boundary → client sees `Error executing tool X` with no reason (111 calls, 33 tools, incl. valid `apply_code_action` / `check_type_stub_freshness`) | `src/python_refactor_mcp/tool_runtime.py:259` |
| 2 | mcp-surface-input-errors-as-backend-failures | high | C1 | Bad positions, missing/dir paths, transaction/stack/history misuse → `[PYRIGHT_BACKEND]/[ROPE_BACKEND] … retry` (397 calls); regression vs 2026-06-19 (`File not found: …`) via `e93207e` | `src/python_refactor_mcp/errors.py:14-38` |
| 3 | mcp-surface-prepare-rename-always-null | high | C1/C6 | Pyright's bare-`Range` reply misparsed as `defaultBehavior` → `null` for every renameable symbol | `backends/pyright_lsp.py:1190` |
| 4 | mcp-surface-unsupported-lsp-silently-empty | high | C1/C6 | Pyright 1.1.411 rejects selectionRange/inlayHint/semanticTokens (`-32601`); tools return `[]`; `apply_type_annotations` inert | `backends/pyright_lsp.py:1023`, `:1245`, `:1304` |
| 5 | mcp-surface-generate-code-broken | high | C1/C6 | References nonexistent `rope.contrib.generate.create_class/…` (hidden by `# pyright: ignore`) → every kind fails | `backends/rope_backend.py:997-1007` |
| 6 | mcp-surface-create-type-stubs-false-success | high | C1/C6 | Returns `true` on any non-error LSP reply; Pyright returns `null`, no stubs written; garbage names also `true` | `backends/pyright_lsp.py:1389-1410` |
| 7 | mcp-surface-failure-id-dead-end | medium | C1 | No log formatter renders `extra={exception_types, traceback_locations}`; Failure IDs are untraceable | `tool_runtime.py:220-233` |
| 8 | mcp-surface-sweep-tools-slow | medium | C1 perf | `dead_code_detection` 30.4 s, `unused_symbol_sweep` 39.7 s on a 137-file repo | `tool_registry.py:1224`, `:1257` |
| 9 | mcp-surface-unbounded-payloads | medium | C1 | `get_symbol_outline` default limit caps roots only → 9,933 nodes / 7.5 MB; other large no-default-limit tools | `server.py:170-174` |
| 10 | mcp-surface-layer-check-false-clean | medium | C6 | Dotted layer patterns never match → `items:[]` with `files_scanned:137`; `import a, b` checks only `b` | `tools/metrics/architecture.py:92-95`, `:122-124` |
| 11 | mcp-surface-default-inliner-overpromise | medium | C3/C6 | "…remove the default from the signature" — preview keeps it; negative `index` Python-indexed | `server.py:210-221` |
| 12 | mcp-surface-preview-drops-file-ops | medium | C6 | `RefactorResult` has no file-op field; `move_module` preview = 0 edits, `module_to_package` = identity edit | `models.py:273-281` |
| 13 | mcp-surface-missing-root-silently-clean | medium | C1 | Nonexistent `root_path` → dead-code/unused sweeps return clean with no `scan_failures`; outline `[]`; type coverage `100.0%` | `tools/search/_helpers.py:122` |
| 14 | mcp-surface-manifest-invalid | medium | C5 | `manifest.json` fails MCPB v0.3: `author`/`repository` strings, no `server`, `tools` wrong shape, undefined `categories`, no runtime/env | `manifest.json:7-19` |
| 15 | mcp-surface-profile-dangling-refs (+ preview-claim-overbroad) | medium | C3 | Instructions + `Related:` cite 23 tools absent from the active profile; "All refactoring tools default to preview" false for 6 immediate-acting tools | `server.py:73-91` |
| 16 | mcp-surface-param-schema-docs (+ unknown-args-ignored) | low | C4 | 0/101 tools document params in-schema; 8 closed sets lack `enum`; `steps` untyped; no `minimum:0` on positions; unknown args silently dropped (98/101) | `tool_registry.py` signatures; `models.py:323` |
| 17 | mcp-surface-numeric-bounds-inconsistent | low | C1 | `limit/offset/depth/count` negatives: raise in some tools, ignored/echoed in others; `undo_refactoring{count:-1}` → "Undid -1 operation(s)", `applied:true` | `util/shared.py:24-36` |
| 18 | mcp-surface-annotation-hints | low | C4 | Whole-file rewriters (`format_code`, `apply_lint_fixes`, …) annotated `destructiveHint:false` | `tool_registry.py:1676-1684` |
| — | resources/prompts capability with none registered | info | C2/C3 | SDK `MCPServer` default; spec-legal | no row |
| — | `.venv` dist-info says 0.4.1 vs source 0.5.0 | info | env | Stale editable metadata in dev venv; run `just reinstall` | no row |

Evidence for each row: the per-check artifact in `ai_docs/audits/20260923-2310/` (call capture + anchor), raw records in `raw/c1_calls.json`.

## C1 — Tool surface

Covered: 108/108 tools. 101 tools got a valid call; the 7 stateful or write-only tools (undo/redo, begin/commit/rollback stack, `refactor_transaction`, `restart_server`) ran as an ordered sequence of error-path and non-writing steps. All were exercised with missing/null/wrong-type/unknown-arg/edge variants (numeric, string, path and list edges). Read-only tools were repeated to check idempotency. Details and the per-tool matrix are in `02_mcp_tools.md`.

| Outcome | Count |
|---|---|
| ok | 383 |
| clear validation error (pydantic) | 430 |
| `[WORKSPACE_RESOLUTION]` (clear) | 332 |
| opaque `Error executing tool X` | 111 → finding 1 |
| `[*_BACKEND]` generic | 397 (396 on caller-input variants + `generate_code`'s valid call) → finding 2 |
| valid calls failing | `apply_code_action` (opaque), `check_type_stub_freshness` (no stub → opaque), `generate_code` (broken) |
| valid calls succeeding with wrong/empty result | `prepare_rename`, `selection_range`, `get_inlay_hints`, `get_semantic_tokens`, `apply_type_annotations`, `create_type_stubs` |

## C2 — Resources / C3 — Prompts

None registered in either profile (`03_mcp_resources.md`, `04_mcp_prompts.md`). The C3 LLM-copy review was done manually because `design:ux-copy` isn't installed here. It produced findings 11 and 15 plus six copy nits, which should be folded into whichever row next touches those docstrings.

## C4 — Schemas

108/108 input and output schemas are valid JSON Schema. Required fields and types are enforced, and naming is consistent. The gaps are findings 16 and 18 (`05_mcp_schemas.md`).

## C5 — Manifest

Finding 14 (`06_mcp_manifest.md`).

## C6 — Parity

There's no under-exposure: every public implementation function is either registered or an internal helper. The over-promise and non-functional tools are findings 3–6, 10, 11 and 12 (`07_mcp_parity.md`). Systemic: 13 call sites in `pyright_lsp.py` turn `Unhandled method` into an empty result, and the client never reads Pyright's advertised capabilities.

## Bad code observed (Directive #3)

| Code | Location | Tracked by |
|---|---|---|
| `# pyright: ignore[reportAttributeAccessIssue]` suppressing a real missing-attribute error | `backends/rope_backend.py:998-1000` | proposed bl-0006 |
| Integration tests that accept `None` / `[]` as success, so dead tools pass CI | `tests/integration/test_end_to_end.py:348`, `:424-429`, `:514-515` | acceptance of proposed bl-0004, bl-0005 |
| "Unhandled method → empty result" swallow pattern, repeated 13× | `backends/pyright_lsp.py:754…1428` | proposed bl-0005 |
| Last-alias-only loop (`for alias in node.names: target_name = alias.name`) | `tools/metrics/architecture.py:123-124` | proposed bl-0011 |
| `extra=` structured-log payload with no formatter to render it (dead diagnostics) | `tool_runtime.py:220-233` | proposed bl-0008 |

## Backlog rows (filed 2026-09-24 as bl-0002 … bl-0019)

Filed through `backlog.mjs add` (doc-audit v15 slim-index); canonical text lives in `ai_docs/backlog.md` + `ai_docs/items/<id>.md` — the tables below are the audit-time proposal.

| id | pri | deps | size | do |
|---|---|---|---|---|
| bl-0002 | High | — | M | **Opaque tool errors drop the reason** — map caller-safe exceptions (ValueError/FileNotFoundError/new `InvalidArgument`) to `ToolError` with the message in `tool_error_boundary`; `apply_code_action` with no actions returns `[]`. [type: bug] [source: mcp-surface-audit-20260923] |
| bl-0003 | High | bl-0002 | M | **Caller-input errors reported as backend outages** — add an input-error class with a caller-safe message; preflight position/file in `_position_request`; rope history/stack/transaction misuse raises it, not `RopeError`. Regression of e93207e. [type: bug] [source: mcp-surface-audit-20260923] |
| bl-0004 | High | — | S | **`prepare_rename` always returns null** — accept Pyright's bare-`Range` reply (and `{range,placeholder}`; only `{defaultBehavior}` → derive range); tighten the integration test to assert a range. [type: bug] [source: mcp-surface-audit-20260923] |
| bl-0005 | High | — | M | **selection_range / inlay hints / semantic tokens silently empty** — record Pyright `initialize` capabilities; return an explicit "unsupported by backend" error (or AST fallback) instead of `[]`; make `apply_type_annotations` not depend on inlay hints. [type: bug] [source: mcp-surface-audit-20260923] |
| bl-0006 | High | — | S | **`generate_code` fails for every kind** — switch to rope `create_generate(kind, …)` (module/package via their real signatures), drop the masking `pyright: ignore`, add an unmocked rope test per kind. [type: bug] [source: mcp-surface-audit-20260923] |
| bl-0007 | High | — | S | **`create_type_stubs` reports success without output** — send Pyright's real argument shape, verify stub files exist, return created paths, error on none; define `output_dir`. [type: bug] [source: mcp-surface-audit-20260923] |
| bl-0008 | Medium | — | S | **Failure IDs are untraceable** — install a stderr formatter that renders the `extra` fields (exception types, traceback locations) of `tool_backend_failure` events. [type: reliability] [source: mcp-surface-audit-20260923] |
| bl-0009 | Medium | bl-0001 | M | **Dead-code sweeps exceed 30 s on a 137-file repo** — batch/concurrent reference lookups in `dead_code_detection` and `unused_symbol_sweep`; target < 10 s on this repo. [type: perf] [source: mcp-surface-audit-20260923] |
| bl-0010 | Medium | — | S | **Unbounded tool payloads (7.5 MB outline)** — make `get_symbol_outline`'s default cap count all nodes; add default limits + `truncated` to module deps, code_metrics, dead_code, search. [type: perf] [source: mcp-surface-audit-20260923] |
| bl-0011 | Medium | — | S | **`check_layer_violations` false-clean on dotted patterns** — prefix-match dotted module patterns, check every `import` alias, resolve relative imports; warn when a layer matches no file. [type: bug] [source: mcp-surface-audit-20260923] |
| bl-0012 | Medium | — | S | **`argument_default_inliner` keeps the default** — set rope `remove=True` (or fix the description) and reject negative `index`. [type: bug] [source: mcp-surface-audit-20260923] |
| bl-0013 | Medium | — | M | **Preview hides file moves/creates** — add file-operation entries to `RefactorResult` from rope `MoveResource`/`CreateResource` changes so `move_module` / `module_to_package` previews show them. [type: bug] [source: mcp-surface-audit-20260923] |
| bl-0014 | Medium | — | S | **Nonexistent scope reads as clean** — `resolve_target_files` reports a `scan_failure` for a missing `root_path`/`file_path`; outline and type coverage stop returning `[]`/100% for missing files. [type: bug] [source: mcp-surface-audit-20260923] |
| bl-0015 | Medium | — | S | **`manifest.json` invalid for MCPB v0.3** — restructure author/repository/server/tools, declare python runtime + env, drop `categories`; add a schema check to `just ci`. [type: bug] [source: mcp-surface-audit-20260923] |
| bl-0016 | Medium | — | S | **LLM copy cites tools absent from the active profile** — make instructions and `Related:` hints profile-aware; state "acts immediately, no preview" on undo/redo/commit/transaction/stubs/restart. [type: docs] [source: mcp-surface-audit-20260923] |
| bl-0017 | Low | — | M | **Tool schemas under-specified** — add per-param descriptions, `enum` for the 8 closed sets, `minimum:0` on positions, a typed `refactor_transaction` step model, `additionalProperties:false`. [type: docs] [source: mcp-surface-audit-20260923] |
| bl-0018 | Low | bl-0003 | S | **Numeric bounds inconsistent across tools** — one validation rule for `limit/offset/depth/max_items/count` (≥1 / ≥0), applied uniformly; `undo/redo count<1` rejected. [type: bug] [source: mcp-surface-audit-20260923] |
| bl-0019 | Low | — | S | **Whole-file rewriters marked non-destructive** — move `format_code`, `apply_lint_fixes`, import rewriters, `apply_code_action`, `apply_type_annotations` to `DESTRUCTIVE_ANNOTATIONS`. [type: bug] [source: mcp-surface-audit-20260923] |

### Detail seeds (anchors · acceptance)

| id | Anchors | Acceptance (regression shape) |
|---|---|---|
| bl-0002 | `tool_runtime.py:237-267`; `errors.py`; `util/shared.py:33,106,122`; `tools/refactoring/code_actions.py:24` | `rename_symbol{new_name:"   "}` returns a tool error naming `new_name` and the reason; `apply_code_action` at an action-less position returns `[]`; no "unexpected exception" traceback on stderr for input errors |
| bl-0003 | `errors.py:14-52`; `backends/pyright_lsp.py:527-545`; `backends/rope_backend.py` (history/stack); `tools/composite.py:116-160` (transaction pre-flight) | `get_type_info{line:-1}` / missing file → input error naming the parameter, no "retry"; `refactor_transaction{steps:[]}` → message states the empty-steps contract; `undo_refactoring` on empty history → "nothing to undo" |
| bl-0004 | `backends/pyright_lsp.py:1177-1225`; `tests/integration/test_end_to_end.py:330-348` | `prepare_rename` on `class User` returns range 12:6-12:10 + placeholder `User`; test asserts non-null |
| bl-0005 | `backends/pyright_lsp.py:321-350` (init), `:1005-1030`, `:1228-1250`, `:1290-1310`; `tools/refactoring/type_annotations.py`; `tests/integration/test_end_to_end.py:408-429,476-515` | against Pyright 1.1.411 the three tools return an explicit unsupported error or non-empty fallback; `apply_type_annotations` annotates `def untyped(p, q)` or states why not |
| bl-0006 | `backends/rope_backend.py:981-1012`; `tests/unit/test_refactoring_tools.py` | preview for kind=function at an unresolved call returns a stub edit; each of the 5 kinds exercised against real rope |
| bl-0007 | `backends/pyright_lsp.py:1389-1410`; `tools/analysis/type_stubs.py:20-26`; `tool_registry.py:329` | `create_type_stubs{package_name:"parso"}` creates `.pyi` files and returns their paths; unknown package → error |
| bl-0008 | `tool_runtime.py:216-234`; `__main__.py` | a forced backend failure's stderr line includes exception types + traceback locations keyed by the Failure ID |
| bl-0009 | `tool_registry.py:1224-1290`; `tools/search/dead_code.py`; `tools/search/unused_symbols.py`; `tools/search/_helpers.py` | both tools < 10 s on this repo (`raw/perf_calls.json` baseline 30.4 s / 39.7 s); results unchanged |
| bl-0010 | `server.py:158-190`; `tools/navigation/outline.py`; `tool_registry.py:1316` | workspace outline response ≤ ~200 KB by default with `truncated:true`; module deps / code_metrics default-capped |
| bl-0011 | `tools/metrics/architecture.py:67-140` | dotted patterns `[["pkg.backends"],["pkg.tools"]]` report the same violations as component patterns; `import a, b` checks both |
| bl-0012 | `server.py:210-221`; `tools/refactoring/signature.py` | preview removes `= 2` from `helper`'s `b`; `index:-1` rejected |
| bl-0013 | `models.py:273-281`; `backends/rope_backend.py` (`_build_result`, `:834-842`, `:953-976`) | `module_to_package` / `move_module` previews list the create/move operations |
| bl-0014 | `tools/search/_helpers.py:122-143`; `server.py:158-190`; `tools/metrics/coverage.py` | nonexistent `root_path` → `scan_failures` entry; nonexistent file → no `100.0%` headline |
| bl-0015 | `manifest.json`; `justfile` / `scripts/` | manifest passes an MCPB v0.3 schema check in `just ci` |
| bl-0016 | `server.py:73-91`; tool docstrings in `tool_registry.py` / `server.py` | per-profile `raw/xref.txt` scan returns 0 dangling refs; the 6 immediate-acting tools say so |
| bl-0017 | `tool_registry.py` signatures (`Annotated[..., Field(description=…)]`); `models.py:323` | schema audit: ≥ 1 param description per tool, 0 enum-like bare strings, `steps` typed |
| bl-0018 | `util/shared.py:24-36`; paginated tools | negative `limit/offset/depth/count` rejected uniformly with a clear message |
| bl-0019 | `tool_registry.py:105-110`, `:1676-1684` | annotations for the listed tools report `destructiveHint:true` |
