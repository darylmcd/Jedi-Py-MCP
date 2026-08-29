# rope-python314-deprecations — Remove upstream Rope deprecation warnings

**row:** `rope-python314-deprecations` · **pri:** `Defer` · **size:** `M`

## Anchors

- `pyproject.toml` (`rope>=1.14` dependency)
- `uv.lock` (locked Rope 1.14.0)
- `tests/unit/test_rope_backend.py` (Rope lifecycle and multi-project coverage)

## Acceptance

- [ ] Adopt an upstream Rope release that removes the Python 3.14 deprecations, or add a bounded compatibility adapter if Python removes an affected API first.
- [ ] Rope project initialization, AutoImport cache generation, and multi-project rename emit no Rope-owned `DeprecationWarning` under Python 3.14.
- [ ] `just ci` passes with the final dependency or adapter.

## Evidence

- The 2026-08-29 `just ci` run emitted Rope-owned warnings from `base/project.py:230` (deprecated source-folder initialization), `contrib/autoimport/sqlite.py:507` (`datetime.utcnow()`), and `base/libutils.py:35` (deprecated `relative`). `pip index versions rope` reported installed/latest 1.14.0, so no upgrade target exists yet.
