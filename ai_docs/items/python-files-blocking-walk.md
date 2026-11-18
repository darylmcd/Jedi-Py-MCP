# python-files-blocking-walk — python_files walks the tree synchronously on the event loop

**row:** `python-files-blocking-walk` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/util/file_filter.py:26`
- `src/python_refactor_mcp/tools/search/_helpers.py:104`

## Acceptance

- [ ] A scan of a large tree does not block other requests (test with a stand-in walk that blocks), or the walk is bounded.

## Evidence

- Found by the PR #228 cold review (Directive #3): pre-existing, shared by the tolerant and the pathless scan.
