# Agent Quickstart

Goal: get an agent productive in this repo in under two minutes.

## 60-Second Bootstrap

1. Read `.github/copilot-instructions.md`.
2. Read `ai_docs/README.md` for project map.
3. Read `ai_docs/runtime.md` for verified commands.
4. Read `ai_docs/workflow.md` for execution flow.
5. Read `CI_POLICY.md` for validation and handoff bar.

## Current Repo State

- Stage status: Stage 3 complete.
- Implemented: Pyright LSP, Jedi backend, rope backend, diff utilities, unit tests.
- Next major milestone: Stage 4 tool orchestration.

## Where Things Are

- MCP lifecycle and tool registration: `src/python_refactor_mcp/server.py`
- Backend runtime config: `src/python_refactor_mcp/config.py`
- Shared models: `src/python_refactor_mcp/models.py`
- Backends: `src/python_refactor_mcp/backends/`
- Tool modules: `src/python_refactor_mcp/tools/`
- Unit tests: `tests/unit/`
- Historical implementation prompt: `ai_docs/archive/python-refactor-mcp-prompt.md`

## Run Before Handoff

- `python -m ruff check .`
- `python -m pyright .`
- `python -m mypy .`
- `python -m pytest tests/unit/ -v`

## Rules Of Thumb

- Keep changes scoped to user request.
- Do not duplicate policy across docs; update canonical owners.
- Record deferred work in `ai_docs/backlog.md` with verification criteria.
