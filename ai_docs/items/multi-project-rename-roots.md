# multi-project-rename-roots — Authorize multi_project_rename additional_roots

**row:** `multi-project-rename-roots` · **pri:** `Medium` · **size:** `M` · **verified:** `de4d87d21cacd62dbbabf881188c339d330b98b7`

## Anchors

- `src/python_refactor_mcp/tool_registry.py:1651-1663`
- `src/python_refactor_mcp/backends/rope_backend.py:1705-1725`
- `tests/unit/test_error_boundary.py:1182-1185`

## Acceptance

- [ ] Operator decision recorded (ADR in `docs/adr/`): which roots a call may name (registered/known roots only, or an explicit allowlist).
- [ ] An `additional_roots` entry outside the authorized set is rejected before any `Project(root)` is opened, with a typed input error.
- [ ] With `apply=true`, no file outside an authorized root is written (test with an unauthorized root).
- [ ] The `additional_roots` entry is removed from `_PATH_LIKE_ALLOWLIST` in `tests/unit/test_error_boundary.py`.
- [ ] Changelog fragment `changed-breaking-*` plus migration note (public contract-care repo).

## Evidence

- `multi_project_rename.additional_roots` opens and, with apply=true, writes in arbitrary client-supplied roots with no authorization check; the drift-guard allowlist names this row.

## Context

Operator decision needed first: cross-project by design, so the policy (known/registered roots only vs explicit allowlist) is a product call. Enforce it after the decision.
