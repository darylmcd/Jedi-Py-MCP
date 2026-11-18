# scan-open-documents-left-open — Tolerant scans leave the documents they opened open

**row:** `scan-open-documents-left-open` · **pri:** `Low` · **size:** `M` · **verified:** `d390a382462fa0905eb6b9aae9c716a628ad6549`

## Anchors

- `src/python_refactor_mcp/tools/analysis/diagnostics.py:163`
- `src/python_refactor_mcp/tools/search/dead_code.py:118`

## Acceptance

- [ ] After either scan the open set returns to its prior size (test), including on failure and cancel.

## Evidence

- Found by the PR #228 implementer: pathless get_diagnostics closes its documents (scan ownership in pyright_lsp.py:200), the two sibling scans still do not (pyright-lsp-no-didclose, partly closed by #228).
