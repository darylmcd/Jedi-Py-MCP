# backend-threading-input-error-doc — Document worker input error propagation

**row:** `backend-threading-input-error-doc` · **pri:** `Low` · **size:** `S` · **verified:** `7167e37ab6bce5e59dc547587724e3bda8eec6e9`

## Anchors

- `src/python_refactor_mcp/backends/_threading.py:1-6`
- `src/python_refactor_mcp/backends/_threading.py:47-52`

## Acceptance

- [ ] The module docstring describes the existing exception behavior.

## Evidence

- The module docstring describes every worker failure as wrapped, but ToolInputError passes through unchanged.
