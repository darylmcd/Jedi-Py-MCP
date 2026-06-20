# refactor-transaction-overlap-line-align — line-align transaction overlap spans before char-diffing

**row:** `refactor-transaction-overlap-line-align` · **pri:** `Medium` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py` (`_changed_char_spans` + the `apply_transaction` overlap guard — aligns old/new lines by index via `zip_longest`).

## Acceptance

- [ ] A transaction where step 1 inserts/deletes whole lines (e.g. `extract_method`, `extract_variable`, `inline_*`) and step 2 edits a non-overlapping later line on the same file does NOT abort with a false overlap.
- [ ] Overlap detection line-aligns first (e.g. `SequenceMatcher` over the line lists) so unchanged-but-shifted lines are not marked touched, then char-diffs only the genuinely changed regions.
- [ ] Regression test: a two-step same-file transaction with a line-count-changing first step commits successfully.

## Evidence

- `cand-refactor-transaction` (#70) code-quality review (2026-06-20): `_changed_char_spans` aligns lines by index, so any line-count change shifts all trailing lines and unrelated lines compare unequal → over-marked as touched → false-positive overlap aborts. 4 of the 5 supported tools (`extract_method`/`extract_variable`/`inline_variable`/`inline_method`) change line counts, so common same-file multi-step transactions falsely abort. **Safe** (conservative abort + rollback, no corruption) but degrades usability.

## Context

- The tool is correct and safe as shipped; this row improves overlap precision so realistic same-file multi-step transactions are not spuriously rejected.
