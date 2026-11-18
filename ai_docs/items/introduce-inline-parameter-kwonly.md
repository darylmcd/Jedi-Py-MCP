# introduce-inline-parameter-kwonly — introduce_parameter/inline_parameter break keyword-only targets

**row:** `introduce-inline-parameter-kwonly` · **pri:** `Low` · **size:** `S` · **verified:** `56acf734d43c24c331918b47ac75a7fbe6956ad4`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py:1200`
- `src/python_refactor_mcp/backends/rope_backend.py:1219`
- `src/python_refactor_mcp/backends/rope_backend.py:1487`
- `src/python_refactor_mcp/backends/rope_backend.py:1501`

## Acceptance

- [ ] introduce_parameter and inline_parameter on a function with a bare star either raise a typed ToolInputError leaving the file untouched, or produce output that ast.parse accepts.
- [ ] A red-first unit test per tool covers a keyword-only target and asserts the applied bytes or the typed error.

## Evidence

- Found by the rope-signature-gaps cold review (PR #220); sibling of rope-signature-override-and-kwonly-gaps, which covers change_signature only. Re-derived on 56acf73: introduce_parameter on def g(a, *, b=1) still yields the unparseable 'def g(a, x=5=5, *):'; neither tool has a keyword-only guard.
