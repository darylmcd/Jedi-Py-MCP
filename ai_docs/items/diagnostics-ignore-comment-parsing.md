# diagnostics-ignore-comment-parsing — Respect the scope of diagnostic ignore comments

**row:** `diagnostics-ignore-comment-parsing` · **pri:** `Medium` · **size:** `S` · **verified:** `7167e37ab6bce5e59dc547587724e3bda8eec6e9`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py:60-85`
- `tests/unit/test_pyright_lsp.py`

## Acceptance

- [ ] Real ignore comments retain their intended semantics and a string containing ignore text does not suppress diagnostics.

## Evidence

- The client regex treats a matching substring anywhere on a line as an ignore comment and discards every diagnostic on that line.
