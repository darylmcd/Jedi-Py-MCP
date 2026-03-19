# AI Docs Index

Purpose: canonical routing map for AI-facing documentation.

## Active Canonical Set

- `../AGENTS.md`: bootstrap order and canonical ownership map
- `../CLAUDE.md`: bootstrap alignment for Claude-style sessions
- `../.github/copilot-instructions.md`: behavior guardrails and policy pointers
- `../CI_POLICY.md`: validation and merge-gating policy
- `workflow.md`: branch/worktree/PR execution flow
- `runtime.md`: verified environment and command facts
- `backlog.md`: open follow-up work only
- `../.cursor/rules/operational-essentials.md`: compact reminder layer aligned with workflow

Read order is defined by `../AGENTS.md`.

## Preferred Active References

- `architecture.md`: compact system architecture reference
- `domains/python-refactor/reference.md`: domain-specific entry point
- `domains/python-refactor/mcp-checklist.md`: MCP best-practice checklist and
	prompt-example template for current and planned tools
- `references/testing.md`: stable test strategy and command reference
- `references/tooling/python.md`: Python/runtime tooling reference
- `procedures/release-handoff.md`: repeatable handoff sequence

## Project Map

- `../src/python_refactor_mcp/server.py`: MCP app lifecycle and tool registration
- `../src/python_refactor_mcp/config.py`: runtime config discovery
- `../src/python_refactor_mcp/models.py`: shared response models
- `../src/python_refactor_mcp/backends/pyright_lsp.py`: Pyright LSP backend
- `../src/python_refactor_mcp/backends/jedi_backend.py`: Jedi fallback backend
- `../src/python_refactor_mcp/backends/rope_backend.py`: rope refactoring backend
- `../src/python_refactor_mcp/util/lsp_client.py`: LSP transport client
- `../src/python_refactor_mcp/util/diff.py`: text edit and atomic write helpers
- `../src/python_refactor_mcp/tools/`: tool modules
- `../tests/unit/`: current automated coverage
- `../tests/integration/`: transport and end-to-end coverage
- `archive/python-refactor-mcp-prompt.md`: stage-by-stage historical implementation prompt

## Organization Rules

- Keep active docs current-state only.
- Keep unfinished work in `backlog.md` only.
- Keep deep history, audits, and point-in-time analyses in `archive/`.
- Keep scratch/session artifacts outside `ai_docs` (for example `.ai-scratch/`).
- Use one canonical owner per concern and link instead of duplicating policy.