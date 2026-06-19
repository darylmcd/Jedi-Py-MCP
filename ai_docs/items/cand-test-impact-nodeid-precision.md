# cand-test-impact-nodeid-precision — Precise pytest node-IDs for test_impact_select

**row:** `cand-test-impact-nodeid-precision` · **pri:** `Low` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/tools/analysis/test_impact.py` (`_node_id` builds `<file>::<name>`, missing the class segment)

(Regression test in `tests/unit/test_test_impact.py` — see Acceptance.)

## Acceptance

- [ ] When a test caller resolves to a method, `_node_id` emits `<file>::<Class>::<method>` (reuse the enclosing-class derivation in `navigation/hierarchy.py`).
- [ ] A class-based test in `tests/unit/` yields a node ID that `pytest <id>` collects to exactly one test.
- [ ] Parametrized cases are documented as still-approximate (slice 2).

## Evidence

- opportunity-scan BRAIN-021 (2026-06-19): `_node_id = f"{file}::{name}"`; the module docstring already states parametrized + nested-class tests are not resolved to pytest collected IDs, so the emitted invocation list can mis-target class-based tests (common in this suite tests/unit/). See `audit-reports/application-brainstorm.md`.

## Context

- First slice only: enclosing-class resolution. Parametrization (`::test[param-id]`) is an explicit slice-2 follow-on. Kill criterion: if call-hierarchy items do not expose enclosing-class context cheaply, document the limitation instead.
