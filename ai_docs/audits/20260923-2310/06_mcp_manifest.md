# 06 — C5 Manifest audit (`manifest.json`)

Reference: MCPB manifest spec v0.3 (`modelcontextprotocol/mcpb` `MANIFEST.md`, fetched 2026-09-23). Offline `mcpb validate` was not run (would require downloading/executing the npm CLI); comparison is field-by-field against the spec.

| Check | Manifest value | Live / spec | Verdict |
|---|---|---|---|
| `manifest_version` | `"0.3"` | spec v0.3 | ok |
| `version` | `0.5.0` | `pyproject.toml` 0.5.0, `__init__.__version__` 0.5.0, live `serverInfo.version` 0.5.0 | ok (kept in sync by `scripts/bump_reinstall.py:88-127`) |
| `author` | string `"darylmcd"` | required **object** `{name, email?, url?}` | **invalid** |
| `repository` | string URL | object `{type, url}` | **invalid** |
| `server` | absent | **required** `{type: "python"\|"uv"\|…, entry_point, mcp_config{command,args,env}}` | **missing** |
| `tools` | object `{transport, command, args}` | array of `{name, description}` | **wrong shape** — launch config placed where the tool list belongs |
| Tool list vs live | no list | live: 75 (refactoring) / 56 (analysis) / 108 union | cannot match; no `tools_generated: true` either |
| `prompts` | absent | live: 0 | consistent |
| `categories` | `["developer-tools","code-analysis"]` | not defined in v0.3 | unknown field |
| Runtime | none | server needs Python ≥ 3.14 + `pyright-langserver` on PATH/venv; `compatibility.runtimes.python` available | **undeclared** |
| Env vars read at startup | none | `PYTHON_REFACTOR_MCP_TOOL_PROFILE` (`config.py:15`), `MAX_WORKSPACES`, `PYRIGHT_LANGSERVER`, `VIRTUAL_ENV` (`ai_docs/runtime.md` Config table) | **undeclared** (no `mcp_config.env` / `user_config`) |
| Launch command | `python -m python_refactor_mcp` | matches registered `~/.claude.json` entry (minus workspace arg) | ok in substance, but in the wrong field |
| Validation in CI | none | `scripts/bump_reinstall.py` only rewrites `"version"`; no schema check | gap |

## Findings

| ID | Sev | Finding | Anchor |
|---|---|---|---|
| mcp-surface-manifest-invalid | medium | `manifest.json` fails MCPB v0.3 on 4 required/typed fields (`author`, `repository`, `server`, `tools`), declares an undefined `categories`, and omits runtime + env declarations. CHANGELOG sells it as "MCP directory compliance" (`CHANGELOG.md:145`), and the repo is PUBLIC, so the defect is externally visible. No validation guards it. | `manifest.json:7`, `:9`, `:13`, `:15-19` |
