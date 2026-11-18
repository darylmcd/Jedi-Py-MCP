# venv-sync-blocked-by-live-mcp — The documented uv sync cannot run beside the repo's own MCP servers

**row:** `venv-sync-blocked-by-live-mcp` · **pri:** `Low` · **size:** `S`

## Anchors

- `ai_docs/runtime.md:53`
- `justfile:105`

## Acceptance

- [ ] A documented command repairs a drifted .venv while the MCP servers run, without deleting installed packages first.
- [ ] A drift check (declared dependency missing from .venv) fails fast with the fix command instead of an xdist usage error inside pytest.

## Evidence

- 2026-11-18 remediate: `just machine-validate ci` failed because the primary .venv lacked the declared pytest-xdist; `uv sync --locked --all-extras` then failed 'failed to remove directory .venv/Lib (os error 32)' and left pyright broken; repaired with `uv export --locked --all-extras --no-hashes --no-emit-project` piped to `uv pip install --reinstall -r`.
