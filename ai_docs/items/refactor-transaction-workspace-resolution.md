# refactor-transaction-workspace-resolution — resolve workspace from a transaction's nested step paths

**row:** `refactor-transaction-workspace-resolution` · **pri:** `Low` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/tools/composite.py` (`refactor_transaction` — the per-step `file_path` lives inside `steps[].args`, not a top-level path param, so the server's `_resolve_backends` cannot use it to pick the workspace).

## Acceptance

- [ ] `refactor_transaction` resolves the workspace from its steps' `file_path`s (extract and route them to the same boundary/registry resolution other tools use) instead of falling through to the most-recent / CLI-fallback workspace.
- [ ] A transaction targeting a file in a non-most-recent loaded workspace runs against the correct workspace rather than raising a confusing "outside workspace root".
- [ ] Regression test with ≥2 loaded workspaces exercises a transaction on the non-most-recent one.

## Evidence

- `cand-refactor-transaction` (#70) cold run-level review (2026-06-20): because the tool's paths are nested in `steps[].args.file_path` (not a top-level `path` param), `_resolve_backends` resolves against `get_most_recent()`/CLI fallback. If the target is in a different loaded workspace, `_resource_for_path` raises "outside workspace root" — **safe** (raises, never corrupts) but confusing, and it reaches the boundary via a different path than every other tool.

## Context

- Latent: only bites multi-workspace sessions where the target file is not in the most-recently-used workspace. No data-loss risk.
