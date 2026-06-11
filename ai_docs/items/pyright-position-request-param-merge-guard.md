# pyright-position-request-param-merge-guard — Harden _position_request against envelope clobber

**row:** `pyright-position-request-param-merge-guard` · **pri:** `Low` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/backends/pyright_lsp.py` (`_position_request`)

## Acceptance

- [ ] Extras merged under the base `{textDocument, position}` envelope (base keys win) OR reserved keys rejected with `ValueError`.
- [ ] Unit test: passing `textDocument`/`position` in `extra_params` cannot clobber the envelope.

## Evidence

- Surfaced during 2026-05-28 backlog-sweep wave-1 (PR #50).

## Context

- Latent only — the sole caller (`get_references`) passes just `context`; current code does `params.update(extra_params)` which lets a future caller clobber the envelope keys.
