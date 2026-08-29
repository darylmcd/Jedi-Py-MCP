# rope-autoimport-utcnow-deprecation — Remove upstream AutoImport UTC warning

**row:** `rope-autoimport-utcnow-deprecation` · **pri:** `Defer` · **size:** `M`

## Anchors

- `pyproject.toml` (`rope>=1.14` dependency)
- `uv.lock` (locked Rope 1.14.0)
- `tests/unit/test_rope_backend.py` (AutoImport cache-generation coverage)

## Acceptance

- [ ] Adopt an upstream Rope release that removes the `datetime.utcnow()` call, or add a bounded compatibility adapter if Python removes the API first.
- [ ] AutoImport cache generation on Python 3.14 emits no Rope-owned `DeprecationWarning`.
- [ ] `just ci` passes with the final dependency or adapter.

## Evidence

- Current focused tests emit `rope/contrib/autoimport/sqlite.py:507: DeprecationWarning`; `pip index versions rope` reports installed/latest 1.14.0 on 2026-08-29, so no upgrade target exists yet.
