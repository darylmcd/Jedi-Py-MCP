# structural-search-abandoned-scan-threads — structural_search fans out unbounded to_thread scans

**row:** `structural-search-abandoned-scan-threads` · **pri:** `Low` · **size:** `S` · **verified:** `d390a382462fa0905eb6b9aae9c716a628ad6549`

## Anchors

- `src/python_refactor_mcp/tools/search/structural.py:196`

## Acceptance

- [ ] At most N scans run at once (test with a counting stand-in).
- [ ] Cancellation does not leave queued scans running.

## Evidence

- Found by the threading-lease review (PR #225): one of two to_thread sites outside _threading.run_in_thread.
