# 04 — C3 Prompt surface + LLM-facing copy review

## Prompts

| Check | Result |
|---|---|
| `prompts/list` (both profiles) | `prompts: []`; `prompts` capability advertised (SDK default — see `03_mcp_resources.md` note) |
| Valid / missing-arg invocation | N/A — none registered |

## Copy review (tool descriptions + server `instructions`)

`design:ux-copy` is **not available** in this environment (not in the skill roster), so the prompt's C3 copy pass was done manually against the live `tools/list` text (`raw/inventory_*.json`) and the cross-reference scan `raw/xref.txt`.

| ID | Sev | Finding | Evidence | Anchor |
|---|---|---|---|---|
| mcp-surface-profile-dangling-refs | medium | The server `instructions` and `Related:` hints name tools the active profile does not advertise. refactoring: instructions cite `call_hierarchy`; 8 descriptions cite absent tools. analysis: instructions cite `rename_symbol`, `extract_method`, `move_symbol` (and "Set apply=True to write changes"); 11 descriptions cite absent tools (e.g. `prepare_rename` → "Use before rename_symbol", `server_status` → `restart_server`). An agent following the copy calls a tool that answers `Unknown tool`. | `raw/xref.txt`; live: refactoring-profile `call_hierarchy` → `Unknown tool: call_hierarchy` | `server.py:73-91` (`_SERVER_INSTRUCTIONS`, one text for both profiles); per-tool docstrings in `tool_registry.py` / `server.py` |
| mcp-surface-preview-claim-overbroad | medium | Instructions state "All refactoring tools default to preview mode (apply=False)". Six tools have no `apply` and act immediately: `undo_refactoring`, `redo_refactoring`, `commit_change_stack`, `refactor_transaction` (commits on success), `create_type_stubs` (writes files by contract), `restart_server`. Their descriptions don't say "no preview / acts immediately". | live schemas: none of the six has an `apply` property | `server.py:83`; `tool_registry.py:1442`, `:1517`, `:329` |
| mcp-surface-default-inliner-overpromise | medium | `argument_default_inliner` copy promises "…then remove the default from the signature"; observed preview keeps it (see `02_mcp_tools.md`). | `02_mcp_tools.md` | `server.py:210-221` |
| (folded into mcp-surface-opaque-input-errors) | — | `apply_code_action`: "omit it [action_title] to list available actions" — at a position with no actions the call errors (opaquely) instead of returning an empty list. | `02_mcp_tools.md` | `tools/refactoring/code_actions.py:24` |
| (folded into mcp-surface-unsupported-lsp-silently-empty) | — | `get_semantic_tokens` ("Returns token type and modifier info for every symbol"), `get_inlay_hints`, `selection_range`, `apply_type_annotations` describe capabilities the bundled Pyright does not provide. | `02_mcp_tools.md` | — |

## Copy nits (no row — below the Low bar, fold into whichever row next touches the docstring)

| Tool | Nit |
|---|---|
| `list_environments` | `Related: get_context` — unrelated tool. |
| `project_search` | "Complements workspace/symbol" — LSP jargon; name the MCP tool (`search_symbols`). |
| `get_declaration` | "For most Python code, this is equivalent to goto_definition" — self-declared redundancy; state when to prefer it or drop it. |
| `structural_search` | `language` param (default `"python"`) is never described; unclear whether any other value is accepted. |
| `create_type_stubs` | Doesn't say where stubs land when `output_dir` is omitted. |
| `begin_change_stack` | Doesn't say which tools enlist in the stack (preview inside a stack did not stage anything observable). |

## Positive observations

| Observation |
|---|
| All 108 descriptions non-empty (100–1261 chars); every positional tool states "Positions are 0-based (line and character offsets, LSP convention)" — the 2026-06-19 finding on undocumented position convention is resolved. |
| Descriptions consistently state preview default, fail-closed shapes, and `scan_failures` semantics. |
