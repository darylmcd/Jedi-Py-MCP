# known-rope-annotations — change_signature strips Python 3 type annotations

**row:** `known-rope-annotations` · **pri:** `Low` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py`

## Acceptance

- [ ] Either rope upstream ships an `ArgumentNormalizer` that preserves annotations (bump + verify), or an in-repo post-pass restores annotations after normalization.
- [ ] Regression test: `change_signature` on an annotated function preserves all parameter annotations.

## Evidence

- Documented inline at the call site in `rope_backend.py`.

## Context

- Blocked on rope upstream (`ArgumentNormalizer` behaviour); no workaround in current rope. Dep recorded here because v15 `deps` cells accept backlog row ids only.
