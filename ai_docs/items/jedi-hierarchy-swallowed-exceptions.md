# jedi-hierarchy-swallowed-exceptions — Document/narrow best-effort exception swallows

**row:** `jedi-hierarchy-swallowed-exceptions` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/backends/jedi_backend.py` (6 `except Exception: pass` sites — lines 397, 477, 622, 719, 762, 769)
- `src/python_refactor_mcp/tools/navigation/hierarchy.py` (2 bare `except (OSError, SyntaxError): pass` — lines 183, 256; the :157 site is documented)

## Acceptance

- [ ] Each swallow site has a narrowed exception type and/or a one-line boundary-marker comment explaining why the swallow is safe.
- [ ] No behaviour change — these are intentional fallbacks.

## Evidence

- doc-audit bad-code-surfacing 2026-05-28.
