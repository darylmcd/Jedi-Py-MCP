# Backlog

Open follow-up items only. Remove entries once verified complete.
Ordered by severity: P0 (bug fixes / security) > P1 (usability / hardening) > P2 (new features) > P3 (advanced) > P4 (stretch) > Tests/Docs.

Best practices analysis: `ai_docs/mcp_best_practices.md`.
Historical plans, audits, and reports removed — all open items consolidated here; originals preserved in git history.

---

## P0 — Security & Bug Fixes

(All items completed.)

---

## P1 — Usability, Hardening & Critical Gaps

(All items completed.)

---

## P2 — Refactoring & Code Quality

- Status: `open`
  Area: complexity / refactoring
  Item: Refactor `get_document_symbols` (CC=24, cognitive=40) — extract nested dict conversion into helper.
  Source: code-review-report (2026-03-28)
  Files: `backends/pyright_lsp.py`

- Status: `open`
  Area: complexity / refactoring
  Item: Refactor `_build_signature_changers` (cognitive=56, nesting=8) — convert to dispatch table pattern.
  Source: code-review-report (2026-03-28)
  Files: `backends/rope_backend.py`

- Status: `open`
  Area: code quality / dedup
  Item: Consolidate `notify_file_changed` — remove duplicate between `composite.py` and `shared.py`.
  Source: code-review-report (2026-03-28)
  Files: `tools/composite.py`, `util/shared.py`

- Status: `open`
  Area: code quality / dead code audit
  Item: Audit `lsp_types.py` — 30+ TypedDict/class definitions appear unused; verify runtime usage patterns.
  Source: code-review-report (2026-03-28)
  Files: `util/lsp_types.py`

- Status: `open`
  Area: code quality / dead code
  Item: Consider removing `severity_to_string` in `lsp_converters.py` if no external consumers exist.
  Source: code-review-report (2026-03-28)
  Files: `util/lsp_converters.py`

- Status: `open`
  Area: tool consolidation
  Item: Merge overlapping tools to reduce tool count below 40: merge `get_type_info`/`get_hover_info`, `rename_symbol`/`smart_rename`, `get_signature_help`/`get_call_signatures_fallback`.
  Source: mcp-compliance-plan GAP-02 (2026-03-28)
  Files: `server.py`, tool modules

- Status: `open`
  Area: error handling
  Item: Audit tool-level fallback `except` blocks for silent error swallowing — add `_LOGGER.debug(..., exc_info=True)` to any that swallow silently.
  Source: mcp-compliance-plan GAP-07 (2026-03-28)
  Files: `tools/analysis/references.py`, `tools/analysis/type_info.py`, `tools/navigation/definitions.py`, `tools/search/symbols.py`

---

## P3 — Known Limitations

- Status: `documented`
  Area: upstream limitation
  Item: `change_signature` strips Python 3 type annotations during normalization. This is a known rope limitation (`ArgumentNormalizer`). Documented in rope_backend.py docstring.
  Source: mcp-server-audit-report #15 (2026-03-28)

---

## P4 — Stretch / Nice-to-Have

- Status: `open`
  Area: feature / refactoring
  Item: **Undo/Redo History** — track and undo/redo refactoring changes with dependency-aware rollback.
  Source: Rope (`rope.base.history.History`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / refactoring
  Item: **Change Stack** — chain multiple refactorings into one atomic change set.
  Source: Rope (`rope.contrib.changestack.ChangeStack`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / refactoring
  Item: **Multi-Project Refactoring** — apply refactorings across multiple Rope projects simultaneously.
  Source: Rope (`rope.refactor.multiproject.MultiProjectRefactoring`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / completion
  Item: **Fuzzy Completion** — enable fuzzy matching for completions (e.g., "ooa" matches "foobar").
  Source: Jedi (`Script.complete(fuzzy=True)`)
  Files: `tools/analysis.py`, `server.py`

- Status: `open`
  Area: feature / search
  Item: **Project-wide Semantic Search** — search across entire project using Jedi's analysis engine.
  Detail: Complements Pyright's `workspace/symbol` with Jedi's `Project.search()` and `Project.complete_search()`.
  Source: Jedi (`Project.search`, `Project.complete_search`)
  Files: `tools/search.py`, `server.py`

- Status: `open`
  Area: feature / analysis
  Item: **Keyword/Operator Help** — documentation for Python keywords and operators.
  Detail: Jedi's `Script.help()` covers keywords like `yield`, `async`, `with` and operators, not just names.
  Source: Jedi (`Script.help`)
  Files: `tools/analysis.py`, `server.py`

- Status: `open`
  Area: feature / analysis
  Item: **Simulate Execution** — simulate calling a callable and return result types.
  Source: Jedi (`Name.execute`)
  Files: `tools/analysis.py`, `server.py`

- Status: `open`
  Area: feature / navigation
  Item: **Sub-definitions** — list sub-definitions of a name (e.g., methods of a class from a reference).
  Source: Jedi (`Name.defined_names`)
  Files: `tools/navigation.py`, `server.py`

- Status: `open`
  Area: feature / environment
  Item: **Environment Management** — discover and manage Python environments/virtualenvs.
  Source: Jedi (`create_environment`, `find_virtualenvs`, `find_system_environments`)
  Files: `tools/analysis.py`, `server.py`

- Status: `open`
  Area: feature / server
  Item: **Restart Server** — discard cached type info and restart Pyright analysis.
  Source: Pyright (`pyright.restartserver`)
  Files: `backends/pyright_lsp.py`, `server.py`

- Status: `open`
  Area: feature / testing
  Item: Add `get_test_coverage_map` tool mapping source symbols to test references.
  Files: new tool module, `models.py`, `server.py`, tests

- Status: `open`
  Area: feature / security
  Item: Add `security_scan` tool with common Python SAST rules.
  Files: new tool module, `models.py`, `server.py`, tests

---

## Tests & Documentation

- Status: `open`
  Area: integration tests
  Item: Add end-to-end integration smoke tests for `introduce_parameter` and `encapsulate_field`.

- Status: `open`
  Area: integration tests
  Item: Expand failure-path integration scenarios (bad line/position, invalid rename target).

- Status: `open`
  Area: documentation
  Item: Complete prompt example bank coverage for all tools in `ai_docs/domains/python-refactor/mcp-checklist.md`.

- Status: `open`
  Area: unit tests
  Item: Finish invalid-input unit-test coverage for tools lacking explicit negative tests.
