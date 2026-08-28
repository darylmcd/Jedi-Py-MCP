# cand-convert-to-dataclass — New tool: convert plain class to @dataclass

**row:** `cand-convert-to-dataclass` · **pri:** `Low` · **size:** `L`

## Anchors

- `src/python_refactor_mcp/util/cst_apply.py` (CST apply foundation)
- `src/python_refactor_mcp/backends/pyright_lsp.py` (field-type inference source)
- new tool module (likely `src/python_refactor_mcp/tools/refactoring/`) + registration

## Acceptance

- [ ] `convert_to_dataclass` tool registered; preview-by-default like other refactoring tools.
- [ ] Field types derived from Pyright inference; class converted to `@dataclass` via CST transform.
- [ ] Unit tests cover a representative class (typed + untyped fields).

## Evidence

- Weaker evidence — proposed candidate; CST apply foundation now exists.
