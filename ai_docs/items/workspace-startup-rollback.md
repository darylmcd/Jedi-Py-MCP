# workspace-startup-rollback — Clean up a partially initialized workspace

**row:** `workspace-startup-rollback` · **pri:** `Medium` · **size:** `S` · **verified:** `7167e37ab6bce5e59dc547587724e3bda8eec6e9`

## Anchors

- `src/python_refactor_mcp/workspace_registry.py:38-58`
- `src/python_refactor_mcp/workspace_registry.py:181-191`
- `tests/unit/test_workspace_registry.py`

## Acceptance

- [ ] A later backend startup failure closes already-started resources and leaves the registry retryable.

## Evidence

- Pyright starts before Jedi and Rope. A later failure prevents the triad from being cached or marked initialized, so ordinary shutdown cannot reap it.
