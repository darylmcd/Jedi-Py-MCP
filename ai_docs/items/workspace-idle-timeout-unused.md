# workspace-idle-timeout-unused — Resolve the unused workspace idle timeout

**row:** `workspace-idle-timeout-unused` · **pri:** `Low` · **size:** `S` · **verified:** `7167e37ab6bce5e59dc547587724e3bda8eec6e9`

## Anchors

- `src/python_refactor_mcp/workspace_registry.py:77-85`
- `tests/unit/test_workspace_registry.py`

## Acceptance

- [ ] The registry exposes only effective lifecycle settings, with tests for the chosen public behavior.

## Evidence

- The registry stores idle_timeout_seconds and has no consumer for it.
