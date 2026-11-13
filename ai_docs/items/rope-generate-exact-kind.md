# rope-generate-exact-kind — Require exact Rope generation kinds

**row:** `rope-generate-exact-kind` · **pri:** `Low` · **size:** `S` · **verified:** `a1b0374f0e2bac50f38f6d3f2e03fd2abbb4531e` · **deps:** `bl-0047`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py:1223-1248`
- `tests/unit/test_rope_backend.py`

## Acceptance

- [ ] Direct Rope generation rejects mixed-case, padded, and unknown kinds with ToolInputError naming kind. The documented lowercase kinds continue to work.

## Evidence

- The direct backend normalizes kind before dispatch and reports unsupported values as RopeError. The MCP GenerateKind literal already requires exact lowercase input.
