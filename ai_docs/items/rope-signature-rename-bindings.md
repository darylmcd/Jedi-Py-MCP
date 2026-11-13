# rope-signature-rename-bindings — Preserve signature rename bindings

**row:** `rope-signature-rename-bindings` · **pri:** `High` · **size:** `M` · **verified:** `7167e37ab6bce5e59dc547587724e3bda8eec6e9`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py:157-162`
- `src/python_refactor_mcp/tools/refactoring/signature.py`
- `tests/unit/test_rope_backend.py`

## Acceptance

- [ ] A preview and applied signature parameter rename preserve the original body binding and both call argument values.

## Evidence

- On base 940b841, renaming b to renamed left b in the body and rewrote f(1, 2) and f(1, b=3) to f(1). The operation composes a remover and adder.
