# integration-stdio-transport-teardown-warning — drain Windows stdio subprocess transport

**row:** `integration-stdio-transport-teardown-warning` · **pri:** `Low` · **size:** `S`

## Anchors

- `tests/integration/conftest.py` (`mcp_session` owns the `stdio_client` context and already documents a Python 3.14 teardown mismatch)

## Acceptance

- [ ] `just test-integration` exits without `PytestUnraisableExceptionWarning` from `BaseSubprocessTransport.__del__` or `_ProactorBasePipeTransport.__del__`.
- [ ] Determine whether the installed MCP SDK or the fixture owns the missing await/close; upgrade the SDK or add explicit fixture cleanup at the owning boundary.
- [ ] Keep real warnings enabled; do not suppress `ResourceWarning`/unraisable exceptions globally.

## Evidence

- Live `just ci` on 2026-08-28: all 27 integration tests passed, then Python 3.14 reported an unclosed proactor subprocess transport during final fixture teardown.
Fresh locked-environment probe on 2026-08-28 found two orphaned pyright.langserver processes plus their Node child holding .venv open after prior MCP/integration activity. The mcp_session fixture also catches and suppresses the anyio different-task RuntimeError around context teardown; remediation must remove that suppression by making context ownership deterministic and must assert no repo-scoped Pyright child remains after the integration suite. A single-test probe exited cleanly, so the defect remains intermittent.
