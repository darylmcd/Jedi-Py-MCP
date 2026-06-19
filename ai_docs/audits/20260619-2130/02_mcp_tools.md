# Track D — MCP Server Surface Audit (static + live probe)

- head_sha: 62f7d3905c92df56208db582c3faaa0f20541d4d
- server: `python-refactor` (Python 3.14+, FastMCP, stdio)
- transport: registered tool surface via ToolSearch (`mcp__python-refactor__*`)
- mode: inline / envelope (orchestrated; no backlog write)

## Tool-count reconciliation (re-derived at HEAD)

- `TOOL_RECORDS` in `tool_registry.py`: **86** pure-delegation records.
- Explicit `@mcp.tool` wrappers in `server.py`: **11** (get_completions, get_inlay_hints,
  get_symbol_outline, argument_normalizer, argument_default_inliner, find_unused_imports,
  get_test_coverage_map, security_scan, security_autofix, structural_replace, server_status).
- **Total = 97.** Matches README.md:11, ai_docs/domains/python-refactor/reference.md, docs/tool-reference.md,
  .ai-doc-audit.md, and the live assertion `tests/unit/test_server.py:14` (`== 97`).
- `tests/unit/test_doc_tool_count_drift.py` enforces every doc count == live surface AND per-category sums.
- **No count-drift finding.** `changelog-tool-count-drift` (shipped #64) stays closed. NOT resurrected.
- Internal-comment drift only: `tool_registry.py` module docstring + `server.py:288` comment say "eight wrappers";
  there are actually **11**. Cosmetic; below Low severity → not filed.

## Live probes (real behavior observed)

| Probe | Call | Observed |
|---|---|---|
| valid read | `search_symbols(query=register_tools)` | clean structured result, correct file:line |
| missing file | `find_references(does_not_exist.py,1,0)` | structured error `File not found: ...` (NOT a crash) — good |
| out-of-bounds position | `find_references(server.py, line=999999, 0)` | empty result `total_count:0` (NO error) — see finding |
| read-only audit | `code_metrics(server.py)` | rich result; `_tool_error_boundary`/`_wrapped` CC=24 cognitive=45 |

Error handling is solid: bad path → clear structured `ValueError`-class error, not a stack trace.

## CAVEAT — live server analyzing a stale workspace snapshot

`get_diagnostics(server.py)` reported `"BackendLiveness"/"ServerStatus"/"structural_replace" is unknown
import symbol`. Verified against HEAD source: all three symbols DO exist (server.py:22,27,37; defined in
models.py / search/structural.py). The live `python-refactor` server is pointed at a stale workspace cache
that predates these symbols — a **server-state artifact, not a repo defect**. Not filed.

## FINDING — position-convention (0-based line/character) is undocumented to consumers

- `models.py:9` `Position` docstring: "0-based line and character offset". Internal convention is 0-based
  across jedi_backend.py (lines 46/54/130), rope_backend.py (168/191), refactoring/helpers.py (30).
- ~60+ position-based tools accept `line:int, character:int` (find_references, goto_definition, rename_symbol,
  get_type_info, call_hierarchy, type_hierarchy, find_implementations, get_signature_help, etc.).
- **Not one of those tool descriptions states the indexing base.** Only `inline_parameter` (server.py:429)
  documents that its *separate* `index` param is 0-based.
- Consumer impact: an LLM client has no in-schema signal that `line`/`character` are 0-based. A 1-based guess
  silently returns wrong or empty results (confirmed: out-of-bounds line returned empty, no error to correct on).
- This is the closest thing the server has to a UX defect: the param schema under-specifies a load-bearing contract.
