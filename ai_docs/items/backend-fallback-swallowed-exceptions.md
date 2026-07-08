# backend-fallback-swallowed-exceptions — Narrow/comment 6 more best-effort exception swallows

**row:** `backend-fallback-swallowed-exceptions` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py:1203` (`prepare_rename` — bare `except Exception: placeholder = Path(absolute_path).stem`; no logging, no boundary comment)
- `src/python_refactor_mcp/server.py:142` (`_maybe_fetch_roots` — per-root URI convert, `except Exception: _LOGGER.warning(...)`, no boundary comment)
- `src/python_refactor_mcp/server.py:147` (`_maybe_fetch_roots` — `session.list_roots()`, `except Exception: _LOGGER.debug(...)`, no boundary comment)
- `src/python_refactor_mcp/backends/rope_backend.py:149` (`initialize` — AutoImport cache pre-warm, `except Exception: _LOGGER.debug(...)`, no boundary comment)
- `src/python_refactor_mcp/backends/rope_backend.py:855` (`autoimport_search` — AutoImport cache generation, `except Exception: _LOGGER.warning(...)`, no boundary comment)
- `src/python_refactor_mcp/tools/analysis/references.py:69` (`_add_context_lines` — per-file read, `except Exception: _LOGGER.debug(...)`, no boundary comment)

## Acceptance

- [ ] Each of the 6 sites either narrows the caught exception type to what can actually be raised, or keeps `Exception` with a one-line boundary-marker comment explaining why the broad catch is safe (same bar as the shipped `jedi-hierarchy-swallowed-exceptions` precedent).
- [ ] No behaviour change — this is a documentation/narrowing pass, not a fix to the fallback logic itself.

## Evidence

- doc-audit bad-code-surfacing 2026-07-08: found while spot-checking the still-open `jedi-hierarchy-swallowed-exceptions` row; the same best-effort-fallback pattern recurs at these 6 additional sites across the Pyright/rope backends and one analysis tool.

## Context

- Sibling row to `jedi-hierarchy-swallowed-exceptions` (jedi_backend.py/hierarchy.py swallows) — kept separate since these 6 sites are in different backend modules and were found in a later audit pass.
