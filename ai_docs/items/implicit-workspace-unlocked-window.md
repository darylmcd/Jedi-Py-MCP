# implicit-workspace-unlocked-window — implicit_workspace reads outside the registry lock

**row:** `implicit-workspace-unlocked-window` · **pri:** `Low` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/workspace_registry.py`

## Acceptance

- [ ] Path-less resolution never returns a workspace that is mid-eviction or mid-initialization (test with a gated shutdown).
- [ ] Decision recorded on selection-before-validation (see workspace-selection-authorized-roots).

## Evidence

- PR #208 cold review: transient, both workspaces were chosen by this session so no wrong-repo leak.

## Notes

PR 211 closed the registered-but-shutting-down window in shutdown_all (eviction and init were already invisible: _evict_lru deletes before the shutdown await, _initialize_workspace registers after initialize). Only acceptance 2 remains: the selection-before-validation decision.
