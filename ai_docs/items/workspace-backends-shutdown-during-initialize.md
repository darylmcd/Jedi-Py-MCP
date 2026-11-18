# workspace-backends-shutdown-during-initialize — WorkspaceBackends.shutdown is a no-op while initialize runs

**row:** `workspace-backends-shutdown-during-initialize` · **pri:** `Low` · **size:** `S` · **verified:** `d390a382462fa0905eb6b9aae9c716a628ad6549`

## Anchors

- `src/python_refactor_mcp/workspace_registry.py:108`

## Acceptance

- [ ] A probe shows whether shutdown during initialize leaks a started backend; fixed with a test, or the registry invariant that makes it unreachable is documented.

## Evidence

- Found by the PR #227 implementer and cold review; unreproduced: through the registry the backend is local to _initialize_workspace and unreachable by retire-on-release.
