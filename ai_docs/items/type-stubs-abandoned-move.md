# type-stubs-abandoned-move — create_type_stubs can abandon a shutil.move mid-mutation

**row:** `type-stubs-abandoned-move` · **pri:** `Low` · **size:** `S` · **verified:** `d390a382462fa0905eb6b9aae9c716a628ad6549`

## Anchors

- `src/python_refactor_mcp/tools/analysis/type_stubs.py:120`

## Acceptance

- [ ] A test cancels the call during the move and shows the move completes or is not started, never half-applied.

## Evidence

- Found by the threading-lease review (PR #225): the second to_thread site outside run_in_thread.
