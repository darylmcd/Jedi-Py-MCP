# Backlog

Open follow-up items only. Remove entries once verified complete.
Ordered by severity: P0 (bug fixes / security) > P1 (usability / hardening) > P2 (new features) > P3 (advanced) > P4 (stretch) > Tests/Docs.

Best practices analysis: `ai_docs/mcp_best_practices.md`.
Historical plans and audits removed — all open items consolidated here; originals preserved in git history.

---

## P0 — Security & Bug Fixes

(All items completed.)

---

## P1 — Usability, Hardening & Critical Gaps

- Status: `done`
  Area: reliability / timeouts
  Item: Add timeouts to Jedi backend operations.
  Completed: 2026-03-28. All 7 `asyncio.to_thread()` calls wrapped with `asyncio.wait_for()` using `JEDI_OPERATION_TIMEOUT_SECONDS` env var (default 10s).

- Status: `done`
  Area: usability / tool design
  Item: Rewrite all 45 tool docstrings with workflow-oriented descriptions.
  Completed: 2026-03-28. All docstrings rewritten with: what, when, key params, related tools.

- Status: `done`
  Area: usability / annotations
  Item: Add `idempotentHint`, `_ADDITIVE` annotation to tool annotations.
  Completed: 2026-03-28. `_READONLY` has `idempotentHint=True`. New `_ADDITIVE` annotation for non-destructive mutations (organize_imports, apply_code_action). `title` field deferred — not yet supported by FastMCP SDK.

- Status: `done`
  Area: usability / server metadata
  Item: Add server instructions to FastMCP constructor.
  Completed: 2026-03-28. Added `instructions` parameter with tool category overview and workflow tips. `version` not supported by current SDK version.

- Status: `done`
  Area: reliability / concurrency
  Item: Add concurrency semaphore for workspace-wide scan operations.
  Completed: 2026-03-28. `asyncio.Semaphore(10)` added to `diagnostics.py`, `outline.py`, and `dead_code.py`.

- Status: `done`
  Area: testing / compliance
  Item: Add MCP protocol contract tests using in-memory transport.
  Completed: 2026-03-28. 10 contract tests in `tests/contract/test_mcp_protocol.py` verifying annotations, descriptions, schema shapes, and validation sets.

- Status: `done`
  Area: observability / logging
  Item: Add timing measurement to all tool functions and backend calls.
  Completed: 2026-03-28. `_tool_error_boundary` now measures and logs elapsed time for every tool call via `ctx.debug`. Backend timing via `util/timing.py` `timed()` context manager.

- Status: `done`
  Area: performance / concurrency
  Item: Parallelize dead_code_detection diagnostics and reference counting.
  Completed: 2026-03-28. Both diagnostic fetch and per-symbol reference counting now use `asyncio.gather` with `Semaphore(10)`.

---

## P2 — High-Value New Features

(All items completed 2026-03-28. 15 new tools added: `inline_method`, `inline_parameter`, `move_method`, `move_module`, `expand_star_imports`, `create_type_stubs`, `generate_code`, `deep_type_inference`, `get_type_hint_string`, `get_syntax_errors`, `code_metrics`, `get_module_dependencies`, `find_unused_imports`, `find_duplicated_code`, `get_type_coverage`.)

---

## P3 — Advanced Analysis & Refactoring

(All items completed 2026-03-28. 15 new tools added: `argument_normalizer`, `argument_default_inliner`, `relatives_to_absolutes`, `froms_to_imports`, `handle_long_imports`, `get_context`, `get_all_names`, `find_errors_static`, `fix_module_names`, `autoimport_search`, `get_coupling_metrics`, `check_layer_violations`, `interface_conformance`, `extract_protocol`, `get_module_public_api`.)

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
