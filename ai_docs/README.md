# AI Docs Index

Purpose: route agents to the right source fast, with minimal re-reading.

## Fast Route

- `quickstart.md`: one-page bootstrap and current state
- `runtime.md`: verified commands and environment facts
- `workflow.md`: execution flow and handoff checklist
- `../CI_POLICY.md`: validation standard
- `backlog.md`: open follow-up work only

Read order is defined by `../AGENTS.md`.

## Canonical Ownership

- `../.github/copilot-instructions.md`: implementation behavior, safety, and definition of done
- `quickstart.md`: session bootstrap shortcut
- `runtime.md`: environment and command facts
- `workflow.md`: execution flow
- `../CI_POLICY.md`: required validation and merge gate policy
- `backlog.md`: open follow-up work only

## Project Map

- `../src/python_refactor_mcp/server.py`: MCP app lifecycle and tool registration
- `../src/python_refactor_mcp/config.py`: runtime config discovery
- `../src/python_refactor_mcp/models.py`: shared response models
- `../src/python_refactor_mcp/backends/pyright_lsp.py`: Pyright LSP backend
- `../src/python_refactor_mcp/backends/jedi_backend.py`: Jedi fallback backend
- `../src/python_refactor_mcp/backends/rope_backend.py`: rope refactoring backend
- `../src/python_refactor_mcp/util/lsp_client.py`: LSP transport client
- `../src/python_refactor_mcp/util/diff.py`: text edit and atomic write helpers
- `../src/python_refactor_mcp/tools/`: tool modules (Stage 4+ implementation target)
- `../tests/unit/`: current automated coverage
- `archive/python-refactor-mcp-prompt.md`: stage-by-stage historical implementation plan

## Doc Rules

- Update canonical docs for current-state facts.
- Keep historical prompts and one-off deep dives in `archive/`.
- Avoid duplicating policy across multiple files.
- When adding a new doc, assign one clear ownership scope and reference it from `AGENTS.md` only if it becomes required bootstrap reading.