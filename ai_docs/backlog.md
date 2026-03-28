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

- Status: `open`
  Area: feature / refactoring
  Item: **Inline Method** — inline a function/method body into all call sites.
  Detail: Current `inline_variable` only handles variables. Rope's `InlineMethod` can inline full function bodies and remove the original definition.
  Source: Rope (`rope.refactor.inline.InlineMethod`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / refactoring
  Item: **Inline Parameter** — remove a parameter by inlining its default value into the body.
  Detail: Rope's `InlineParameter` removes a parameter from the signature and replaces its usage inside the function with the default value.
  Source: Rope (`rope.refactor.inline.InlineParameter`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / refactoring
  Item: **Move Method** — move a method from one class to another.
  Detail: Current `move_symbol` only handles global symbols via `MoveGlobal`. Rope's `MoveMethod` moves a method between classes, creating a delegate in the original.
  Source: Rope (`rope.refactor.move.MoveMethod`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / refactoring
  Item: **Move Module** — move/rename an entire module or package, updating all imports.
  Detail: Rope's `MoveModule` handles full module/package relocation with project-wide import updates.
  Source: Rope (`rope.refactor.move.MoveModule`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / imports
  Item: **Expand Star Imports** — replace `from x import *` with explicit named imports.
  Detail: Critical for code quality. Rope's `ImportOrganizer.expand_star_imports()` resolves star imports to explicit names.
  Source: Rope (`rope.refactor.importutils.ImportOrganizer.expand_star_imports`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / analysis
  Item: **Create Type Stubs** — generate `.pyi` stub files for untyped packages.
  Detail: Pyright's `pyright.createtypestub` command generates type stub files for third-party packages lacking type information.
  Source: Pyright (`pyright.createtypestub`)
  Files: `backends/pyright_lsp.py`, `tools/analysis.py`, `server.py`

- Status: `open`
  Area: feature / generation
  Item: **Code Generation** — generate missing classes, functions, variables, modules, and packages from usage sites.
  Detail: Rope's `rope.contrib.generate` module creates skeleton definitions for names referenced but not yet defined.
  Source: Rope (`rope.contrib.generate`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / analysis
  Item: **Deep Type Inference** — follow imports and statements to resolve final types.
  Detail: Jedi's `Script.infer()` goes deeper than `get_type_info`, following imports and assignments to their ultimate definitions.
  Source: Jedi (`Script.infer`)
  Files: `tools/analysis.py`, `server.py`

- Status: `open`
  Area: feature / analysis
  Item: **Get Type Hint String** — return annotation strings like `Iterable[int]` for symbols.
  Detail: Jedi's `Name.get_type_hint()` returns ready-to-use type annotation strings, useful for adding missing type hints.
  Source: Jedi (`Name.get_type_hint`)
  Files: `tools/analysis.py`, `server.py`

- Status: `open`
  Area: feature / diagnostics
  Item: **Get Syntax Errors** — detect syntax errors via Jedi's parser.
  Detail: Jedi's `Script.get_syntax_errors()` complements Pyright diagnostics with an independent syntax check.
  Source: Jedi (`Script.get_syntax_errors`)
  Files: `tools/analysis.py`, `server.py`

- Status: `open`
  Area: feature / metrics
  Item: Add `code_metrics` tool (cyclomatic complexity, cognitive complexity, nesting depth, LoC, parameter count).
  Detail: No way to automatically flag complexity hotspots. Uses stdlib `ast` only.
  Files: `tools/metrics.py` (new), `models.py`, `server.py`, `tests/unit/test_metrics_tools.py` (new)

- Status: `open`
  Area: feature / architecture
  Item: Add `get_module_dependencies` tool with import graph and circular dependency detection.
  Detail: Parse `ast.Import`/`ast.ImportFrom` nodes. Resolve to file paths. Detect cycles via DFS.
  Files: `tools/metrics.py`, `models.py`, `server.py`, tests

- Status: `open`
  Area: feature / search
  Item: Add `find_unused_imports` tool.
  Detail: Use Pyright diagnostics filtered for `reportUnusedImport`. AST fallback for files not analyzed by Pyright.
  Files: `tools/search.py`, `models.py`, `server.py`, tests

- Status: `open`
  Area: feature / search
  Item: Add `find_duplicated_code` / clone detection tool.
  Detail: Normalize function bodies via `ast.dump()`, hash, group by identical hashes. Structural duplicates use placeholder names before hashing.
  Files: `tools/metrics.py`, `models.py`, `server.py`, tests

- Status: `open`
  Area: feature / analysis
  Item: Add `get_type_coverage` tool reporting annotation completeness.
  Detail: Walk AST function definitions. Check return annotations and parameter annotations. Report percentages and unannotated symbols.
  Files: `tools/metrics.py`, `models.py`, `server.py`, tests

---

## P3 — Advanced Analysis & Refactoring

- Status: `open`
  Area: feature / refactoring
  Item: **Argument Normalizer** — normalize call-site arguments to match definition order.
  Detail: Rope's `ArgumentNormalizer` reorders keyword arguments at call sites to match the function signature parameter order.
  Source: Rope (`rope.refactor.change_signature.ArgumentNormalizer`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / refactoring
  Item: **Argument Default Inliner** — inline a parameter's default value into all call sites that omit it, then remove the default.
  Detail: Rope's `ArgumentDefaultInliner` pushes defaults to call sites.
  Source: Rope (`rope.refactor.change_signature.ArgumentDefaultInliner`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / imports
  Item: **Relatives to Absolutes** — convert all relative imports to absolute imports.
  Source: Rope (`rope.refactor.importutils.ImportOrganizer.relatives_to_absolutes`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / imports
  Item: **Froms to Imports** — convert `from module import name` to `import module` style.
  Source: Rope (`rope.refactor.importutils.ImportOrganizer.froms_to_imports`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / imports
  Item: **Handle Long Imports** — break long import lines per project preferences.
  Source: Rope (`rope.refactor.importutils.ImportOrganizer.handle_long_imports`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / navigation
  Item: **Get Context (enclosing scope)** — return the enclosing function/class/module at a position.
  Detail: Jedi's `Script.get_context()` provides scope-aware context useful for understanding code structure.
  Source: Jedi (`Script.get_context`)
  Files: `tools/navigation.py`, `server.py`

- Status: `open`
  Area: feature / navigation
  Item: **Get All Names** — list all defined names in a file with optional nested scopes.
  Detail: Jedi's `Script.get_names()` is broader than `get_symbol_outline`, including references and nested scopes.
  Source: Jedi (`Script.get_names`)
  Files: `tools/navigation.py`, `server.py`

- Status: `open`
  Area: feature / diagnostics
  Item: **Find Errors (static)** — Rope's static analysis for bad name/attribute accesses.
  Detail: Complements Pyright diagnostics with Rope's own analysis via `rope.contrib.finderrors.find_errors()`.
  Source: Rope (`rope.contrib.finderrors`)
  Files: `tools/analysis.py`, `server.py`

- Status: `open`
  Area: feature / refactoring
  Item: **Fix Module Names** — batch-rename modules to conform to PEP 8 lowercase naming.
  Source: Rope (`rope.contrib.fixmodnames.FixModuleNames`)
  Files: `tools/refactoring.py`, `server.py`

- Status: `open`
  Area: feature / search
  Item: **AutoImport Cache** — SQLite-backed cache of all global names for fast auto-import suggestions.
  Detail: Rope's `rope.contrib.autoimport.AutoImport` provides project-wide cached auto-import search, faster than Pyright for large projects.
  Source: Rope (`rope.contrib.autoimport.AutoImport`)
  Files: `tools/search.py`, `server.py`

- Status: `open`
  Area: feature / architecture
  Item: Add `get_coupling_metrics` (afferent/efferent coupling, instability per module).
  Detail: Depends on `get_module_dependencies` import graph. Ca = importers count, Ce = imports count, I = Ce/(Ca+Ce).
  Files: `tools/metrics.py`, `models.py`, `server.py`, tests

- Status: `open`
  Area: feature / architecture
  Item: Add `check_layer_violations` to enforce import direction against declared layering.
  Detail: Accept `layers: list[list[str]]`. Walk import graph. Flag edges from lower layers to higher layers.
  Files: `tools/metrics.py`, `models.py`, `server.py`, tests

- Status: `open`
  Area: feature / architecture
  Item: Add `interface_conformance` tool to detect implicit protocol conformance.
  Detail: Given class names, extract method signatures via `ast`. Compare for common/unique methods and signature mismatches.
  Files: `tools/metrics.py`, `models.py`, `server.py`, tests

- Status: `open`
  Area: feature / refactoring
  Item: Add `extract_protocol` tool to generate Protocol class from common methods.
  Detail: Reuse `interface_conformance` logic. Generate Protocol source string.
  Files: `tools/metrics.py`, `models.py`, `server.py`, tests

- Status: `open`
  Area: feature / navigation
  Item: Add `get_module_public_api` tool returning only exported symbols.
  Detail: Thin wrapper over `get_symbol_outline`. Filter `_`-prefixed names. Respect `__all__` if present.
  Files: `tools/navigation.py`, `server.py`, tests

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
