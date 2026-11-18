# rope-same-name-defs-header-rewrite — Rope signature ops corrupt same-named defs

**row:** `rope-same-name-defs-header-rewrite` · **pri:** `Medium` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py`
- `src/python_refactor_mcp/util/param_rename.py`

## Acceptance

- [ ] add/remove/reorder/normalize/inline_default on a name defined more than once either refuse with a typed error (file untouched) or rewrite only the target def.
- [ ] Tests: overload stubs, property getter/setter, conditional redefinition, plain redefinition; a same-named method in another class is not refused.

## Evidence

- Cold review of PR #209 reproduced: rename index=1 on two `def f(a, b)` rewrote both headers; @overload stubs gained a spurious default; a property getter gained the new parameter. The rename pass now refuses, the other operations still corrupt.
