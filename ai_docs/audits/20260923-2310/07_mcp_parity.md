# 07 — C6 Capability ↔ surface parity

Evidence: `harness/parity.py.txt` (AST scan of `src/python_refactor_mcp/tools/**` + `backends/**` vs registry), `harness/lsp_probe.py.txt` (raw Pyright LSP), `harness/gen_probe.py.txt` (raw rope), `raw/xref.txt`.

## A. Implementation → surface (under-exposure)

| Check | Result |
|---|---|
| Public functions in `tools/**` not reachable from `tool_registry.py` / `server.py` | 21 — all internal helpers (`_helpers.py`, `_converter_preflight.py`, `helpers.py`, …) consumed by registered tools. No orphaned capability. |
| Backend public methods unused outside `backends/` | 1 — `PyrightLSPClient.ensure_file_open` (internal lifecycle). No gap. |
| Pyright LSP features used | definition, declaration, typeDefinition, implementation, references, hover, completion, signatureHelp, documentSymbol, workspace/symbol, rename, prepareRename, callHierarchy, codeAction, documentHighlight, foldingRange, diagnostics, `pyright.createtypestub`, `pyright.restartserver` |
| rope refactorings used | rename, extract method/variable, inline, move (global/method/module), change signature (+ normalize / inline default), introduce factory / parameter, encapsulate field, local→field, method object, module→package, restructure, use function, generate, import utils (froms/relatives/long/expand/organize), history (undo/redo), autoimport, finderrors, fix module names |
| Jedi used | infer, goto, help, names, context, search/complete_search, syntax errors, environments, execute |
| Conclusion | **No under-exposure finding.** The catalog covers the three backends broadly; the parity problems are over-promise (B) and advertised-but-non-functional (C). |

## B. Surface → implementation (over-promise)

| ID | Sev | Tool / text | Promise | Reality | Anchor |
|---|---|---|---|---|---|
| mcp-surface-default-inliner-overpromise | medium | `argument_default_inliner` | "…then remove the default from the signature" | default kept (rope `ArgumentDefaultInliner.remove=False`) | `server.py:210-221` |
| mcp-surface-preview-drops-file-ops | medium | `move_module`, `module_to_package` preview | preview "visualize … before applying" | file moves/creations absent from `RefactorResult` | `models.py:273-281` |
| mcp-surface-preview-claim-overbroad | medium | server `instructions` | "All refactoring tools default to preview mode" | 6 tools act immediately | `server.py:83` |
| mcp-surface-profile-dangling-refs | medium | instructions + `Related:` hints | names tools as available | 4 + 19 references to tools absent in the active profile | `server.py:73-91` |
| mcp-surface-layer-check-false-clean | medium | `check_layer_violations` | "Check import directions against declared layering rules" (example: "presentation", "domain") | layer patterns match **one path/dotted component** only (`pattern in parts`), so a natural dotted module pattern (`python_refactor_mcp.backends`) never matches and returns `items:[]` with `files_scanned:137` — indistinguishable from a clean architecture. `import a, b` checks only the last alias (`for alias in node.names: target_name = alias.name`). Relative imports (`from . import x`) are skipped. | `tools/metrics/architecture.py:92-95`, `:122-124` |

Capture (`harness/perf2.py.txt`, repo copy): `layers=[["python_refactor_mcp.backends"],["python_refactor_mcp.tools"]]` → `{"items":[],"files_scanned":137}`; same ordering as components `[["backends"],["tools"]]` → violations reported (e.g. `tools/analysis/test_impact.py` → backends).

## C. Advertised but non-functional

| ID | Sev | Tool | Observed | Root cause | Anchor |
|---|---|---|---|---|---|
| mcp-surface-unsupported-lsp-silently-empty | high | `selection_range`, `get_inlay_hints`, `get_semantic_tokens`, `apply_type_annotations` | always `[]` / "No inferable type annotations found" | Pyright 1.1.411 `-32601 Unhandled method` → mapped to `[]`; the client never reads the server's `initialize` capabilities (no stored capability set) | `backends/pyright_lsp.py:1023`, `:1245`, `:1304` |
| mcp-surface-prepare-rename-always-null | high | `prepare_rename` | always `null` | bare-`Range` response misparsed as `defaultBehavior` | `backends/pyright_lsp.py:1190` |
| mcp-surface-generate-code-broken | high | `generate_code` | always `[ROPE_BACKEND]` | nonexistent rope API (`create_class` …), masked by `# pyright: ignore` | `backends/rope_backend.py:997-1007` |
| mcp-surface-create-type-stubs-false-success | high | `create_type_stubs` | `true`, no files | success = "no JSON-RPC error"; Pyright returns `null` and writes nothing | `backends/pyright_lsp.py:1389-1410` |

Systemic note: 13 call sites in `pyright_lsp.py` convert `Unhandled method` into an empty result (`:754, :964, :980, :996, :1023, :1118, :1138, :1182, :1245, :1304, :1368, :1405 (raises), :1428`). Beyond the three confirmed dead features, any future Pyright capability removal will degrade silently the same way. Fix direction: capture `InitializeResult.capabilities` at startup, and either hide unsupported tools from `tools/list` or return an explicit "unsupported by backend" error.
