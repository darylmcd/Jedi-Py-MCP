# real-registry-ctx-test-helper-spies — Real-registry test helper never runs real init

**row:** `real-registry-ctx-test-helper-spies` · **pri:** `Low` · **size:** `S` · **verified:** `93cd1b324525daf60c5666c8f1107db9ce846b21`

## Anchors

- `tests/unit/test_error_boundary.py:820-831`

## Acceptance

- [ ] `_real_registry_ctx` either exercises real initialization (a seam that patches only the backend constructors / `_initialize_workspace` inner step, leaving `get_backends` real) or is renamed and documented as a root-resolution-only fixture.
- [ ] Tests that claim real-registry behaviour (mixed-workspace, escape, nested-root) use the real-init variant, or their docstrings stop claiming it.

## Evidence

- The helper replaces `registry.get_backends` with an `AsyncMock` spy returning root-matched fake backends, so tests built on it never run the registry's initialization, eviction or locking.

## Context

- Noted while planning `bl-0056`; `diff-preview-root-only` adds proper real-registry tests for its own mode.
