# stale-server-py-doc-pointers — Repoint docs naming server.py as the registration layer

**row:** `stale-server-py-doc-pointers` · **pri:** `Low` · **size:** `S` · **verified:** `b935c2cda00eea0c75a6e613ff7b8f416f543391`

## Anchors

- `ai_docs/prompts/deep-review-refactor.md:4`
- `ai_docs/references/mcp_best_practices/design-and-architecture.md:28`

## Acceptance

- [ ] Both files name `tool_registry.py` (TOOL_RECORDS) as the tool registration layer and `server.py` as lifecycle and entrypoint.

## Evidence

- PR #214 moved every tool delegate and record into `tool_registry.py`; these two docs still call `server.py` the registration layer.
