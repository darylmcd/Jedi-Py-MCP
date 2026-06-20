# Changelog

All notable changes to Jedi-Py-MCP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Category order used in each release: **Fixed** → **Changed — BREAKING** → **Changed** → **Added** → **Maintenance**. Omit empty categories.

## [Unreleased]

### Fixed

- **Fixed:** `change_signature` no longer strips PEP 484/585 parameter type annotations. rope's `ArgumentNormalizer`/`ArgumentAdder` re-emit the parameter list without annotations on `normalize`/`rename`/`reorder`/`add`/`remove`; a LibCST post-pass (`tools/refactoring/signature_annotations.py`) now re-attaches them on the definition — by parameter name, and by original position for all-`rename` operation sets (conservatively skipped under combined position-shuffling ops to avoid attaching a wrong type). Corrected edits are applied through rope's rollback-capable path. Known residual: rope still drops parameter *default values* (tracked by `cand-change-signature-cst`). Resolves the annotation half of `known-rope-annotations` / architecture Known Gaps #1.
- **Fixed (security):** the `structural_search` / `structural_replace` matcher-pattern compiler now validates the pattern against a strict AST node-type allowlist (matcher calls on `m`/`cst`, literals, and the `|`/`~` operators only) and rejects dunder-attribute access and subscripts. The previous `ast.Name`-only check let attribute/subscript chains on literals (e.g. `().__class__.__bases__[0].__subclasses__()...`) reach object internals and execute arbitrary code through the pattern `eval`. Hardened in `tools/search/structural.py::compile_pattern`; regression test added.
- **Fixed:** `rope.restructure` error messages now interpolate the underlying exception. The previous message was a literal non-f-string (`"rope restructure failed: {exc}"`) that never substituted the cause; surfaced and fixed during the `run_in_thread` extraction (#51).

### Changed

### Added

- **Added:** New tool `format_code` — thin async wrapper around `ruff format --stdin-filename` that respects the project's `pyproject.toml`/`ruff.toml`, supports single-file and batch mode, and follows the existing preview/apply contract (whole-file replace edit per changed file; unchanged files are omitted). Closes `cand-format-code`. Server surface: 87 → 88 tools.
- **Added:** New tool `apply_lint_fixes` — async wrapper around `ruff check --fix-only --stdin-filename` that mirrors `format_code`'s preview/apply contract and adds `unsafe_fixes` for ruff's unsafe auto-fix tier. Closes the auto-fix loop with `get_diagnostics` / `find_errors_static`. Closes `cand-apply-lint-fixes`. Server surface: 88 → 89 tools.
- **Added:** New tool `unused_symbol_sweep` — project-wide audit of the public export surface for symbols with zero cross-file references. Covers `__all__`-listed names (or all non-underscore module-level names when `__all__` is absent) regardless of decoration, skipping externally-registered symbols (decorators containing `mcp`/`tool`). Complements `dead_code_detection`, which scopes to undecorated module-level symbols. Returns paginated `DeadCodeItem` results with confidence scores. Closes `cand-unused-symbol-sweep`. Server surface: 91 → 92 tools.
- **Added:** New tool `extract_superclass` — pull a named subset of plain methods and class-level attributes up into a new base class, inserted immediately before the source class, via the in-repo LibCST foundation (rope 1.14 ships no `ExtractSuperclass`). Rejects unsupported member kinds (`@classmethod`/`@staticmethod`/`@property` methods, `__slots__`, `__init__`-assigned instance attributes) with a clear error. Defaults to preview mode (`apply=False`). Related: `extract_method`, `move_symbol`. Closes `cand-extract-superclass`. Server surface: 92 → 93 tools.
- **Added:** New tool `test_impact_select` — given a list of changed symbol anchors (`file_path`, `line`, `character`), traverses the call-hierarchy callers graph per anchor and returns the pytest tests that transitively exercise those symbols. Filters callers to test files and emits best-effort `<file_path>::<symbol>` node IDs (parametrized/nested-class tests are not resolved to pytest's exact collected IDs). Related: `call_hierarchy`, `get_test_coverage_map`. Closes `cand-test-impact-selector`. Server surface: 93 → 94 tools.
- **Added:** New tool `security_autofix` — LibCST codemod that rewrites unsafe `yaml.load(stream)` (SEC022) to `yaml.safe_load(stream)`. Conservative: calls passing an explicit `Loader=` (keyword or second positional) are skipped and counted, since an explicit loader may be deliberate. Targets the literal `yaml.load` attribute call (aliases / `from yaml import load` are a documented follow-up). Defaults to preview mode (`apply=False`); annotated `_DESTRUCTIVE` because `safe_load` changes runtime behavior. Complements `security_scan` (which detects but cannot fix). Closes `cand-security-autofix`. Server surface: 94 → 95 tools.
- **Added:** New tool `server_status` — read-only health/provenance snapshot: server version, known workspace roots, CLI workspace root, and per-workspace backend liveness (Pyright subprocess up, Jedi/rope ready). Surfaces a `degraded` flag when no loaded workspace has a live Pyright, the condition under which analysis silently falls back to Jedi. Probes are cheap (cached state, no analysis round-trip) and it works with zero workspaces loaded. Closes `cand-server-status`. Server surface: 95 → 96 tools.
- **Added:** New tool `structural_replace` — LibCST codemod that finds nodes with the same matcher DSL as `structural_search` and rewrites them via `$name` capture templates (capture sub-nodes with `m.SaveMatchedNode(<matcher>, "name")`, reference them as `$name` in the replacement). Expression-position matches only; requires `file_path`/`file_paths`; preview-by-default (`apply=True` writes atomically + refreshes diagnostics); `_DESTRUCTIVE`. The find/replace complement to `structural_search`. Closes `cand-structural-replace`. Server surface: 96 → 97 tools.

### Maintenance

- **Maintenance:** Reconciled stale server-wide tool counts to the canonical surface (`README.md` and `.ai-doc-audit.md` said 91; `reference.md` is the single source). All now read 96 after the two additions above. Closes `changelog-tool-count-drift`.
- **Maintenance:** Completed the prompt-example bank in `ai_docs/domains/python-refactor/mcp-checklist.md` — every tool on the current server (87 total across navigation, analysis, search, refactoring, metrics, history, and infrastructure) now has a Goal / Validation / Chaining prompt triple. Closes `mcp-checklist-prompts`.
- **Maintenance:** Rehomed the new-tool roadmap from `mcp-checklist.md` D.1/D.2 into `ai_docs/backlog.md` (governed by the existing Agent contract) with verified `blocker` values: dropped two non-viable entries (`cand-extract-superclass` — rope 1.14 has no `ExtractSuperclass`; `cand-find-cyclic-imports` — redundant with `get_module_dependencies.circular_dependencies`) and re-flagged four rope-assumed candidates as `custom-cst`. `mcp-checklist.md` now points at the backlog for candidate storage and keeps only the intake process.
- **Maintenance:** Replaced the 83 identical per-tool wrapper functions in `server.py` with a declarative registration table in new `tool_registry.py`; the registrar applies `_tool_error_boundary` + `mcp.tool(annotations=…)` per record. `server.py` drops from 1815 to ~430 lines while the ~8 non-trivial wrappers (e.g. `get_completions`, `get_inlay_hints`, `security_scan`) stay explicit. Tool surface and schemas unchanged. Closes `server-tool-registration-table` (#52).
- **Maintenance:** Extracted a shared `run_in_thread` async helper into new `backends/_threading.py`, eliminating 47 duplicate `asyncio.wait_for` / `asyncio.to_thread` / `except` boilerplate blocks across `RopeBackend` (30) and `JediBackend` (17). Backend error messages now use a uniform `"<op_name> failed: <exc>"` form. No behaviour change. Closes `backend-threaded-decorator` (#51).
- **Maintenance:** Extracted a `_position_request` helper in `PyrightLSPClient` to deduplicate the normalize / open / request / error boilerplate shared across 12 `textDocument/*` position methods, reducing `pyright_lsp.py` by ~59 lines. No behaviour change. Closes `pyright-lsp-position-request-helper` (#50).
- **Maintenance:** Decomposed the shared `_tool_error_boundary`/`_wrapped` decorator (the repo's highest-complexity closure) into `_resolve_backends` (multi-ctx lookup + lazy MCP root-fetch + primary-path extraction + registry resolution) and `_validate_params` (path + identifier validation); the wrapper retains only timing + `BackendError`→`ValueError` translation. Wrapper cyclomatic/cognitive/nesting drops 24/45/5 → 7/9/4. No behaviour change. Closes `refactor-tool-error-boundary-decomposition`.

## [0.4.1] - 2026-04-24

### Fixed

- **Fixed:** Deterministic workspace resolution for multi-path tools (e.g., `move_symbol(source_file, destination_file)`). `_PATH_PARAMS`, `_LIST_PATH_PARAMS`, and `_IDENTIFIER_PARAMS` moved from `frozenset` to ordered `tuple` with source/subject entries explicitly ahead of destination entries; contract test now asserts both membership and ordering invariants (#27).
- **Fixed:** Lazy MCP roots-fetch state now scoped to the lifespan via `MultiWorkspaceContext.roots_fetched`. Previously leaked across in-process `WorkspaceRegistry` instances — a latent bug for tests that recreate the registry (#27).
- **Fixed:** Removed unreachable second early-return branch and dead `_roots_dirty` flag in `_maybe_fetch_roots` (#27).

### Changed

- **Changed:** Hoisted two PLC0415-suppressed lazy imports (`apply_limit` in `server.get_completions`, `RefactorResult` in `util.shared.attach_post_apply_diagnostics`) after verifying no circular-import risk (#27).

### Maintenance

- **Maintenance:** Full doc-audit first pass — added `justfile` (14 recipes) as canonical task runner; restructured `README.md` from 438-line content node to 58-line navigation node; extracted `docs/setup.md`, `docs/usage.md`, `docs/tool-reference.md`; rewrote `ai_docs/backlog.md` with Agent contract, ISO-8601 `updated_at`, stable row ids, and separated standing rules; added `<!-- purpose -->` headers across `ai_docs/` (#25).
- **Maintenance:** Migrated repository doc-audit context to schema 4 and added the required planning router. Aligned `AGENTS.md`, `CLAUDE.md`, runtime/testing references, and setup docs with current bootstrap contracts. Added tracked Cursor and VS Code MCP config files; `.vscode/mcp.json` now allowed through `.gitignore` (#26).
- **Maintenance:** Standardized `ai_docs/` — fixed stale tool counts, cleaned backlog, moved best practices into `ai_docs/references/` (#24).
- **Maintenance:** Removed stale root `mcp.json` — editor MCP configs live under `.vscode/` and `.cursor/` (#23).

## [0.4.0] - 2026-03-30

### Added

- **Added:** Multi-workspace architecture. `WorkspaceRegistry` with LRU eviction lets the MCP server handle multiple workspace roots in a single session, eliminating the single-root startup constraint (#22).

### Fixed

- **Fixed:** 18 MCP-server audit findings addressed in a single pass (#22).

### Maintenance

- **Maintenance:** Version bump to 0.4.0 (#22).

## [0.3.0] - 2026-03-30

### Added

- **Added:** 15 new tools from P2–P4 backlog items, bringing the tool surface to 90 (#21).

### Changed

- **Changed:** Code-quality refactoring pass alongside the tool additions (#21).

### Maintenance

- **Maintenance:** Version bump to 0.3.0 (#21).

## [0.2.0] - 2026-03-28

### Added

- **Added:** 30 new tools from P2/P3 backlog items (45 → 75 total) (#17).

### Fixed

- **Fixed:** 19 MCP-server audit issues — LSP capabilities, false positives, stale diagnostics (#19).

### Changed

- **Changed:** Dead-code removal, private-access export fixes, complexity reduction, and test-helper deduplication (#18).

### Maintenance

- **Maintenance:** Docs consolidation — moved unfinished items to backlog; rebuilt review prompt for the 75-tool surface (#20).
- **Maintenance:** Ruff error cleanup and import-sort auto-fixes across tool modules and tests (#21 preparatory work).
- **Maintenance:** Version bump to 0.2.0.

## [0.1.1] - 2026-03-28

### Changed

- **Changed:** MCP best-practices compliance — tool annotations, descriptions, timeouts, concurrency controls, and test coverage (#14).

### Maintenance

- **Maintenance:** Removed archived docs; added Claude Code config (#16).
- **Maintenance:** Version bump to 0.1.1 (#15).

## [0.1.0] - 2026-03-28

### Added

- **Added:** Initial release — MCP server for Python refactoring exposing 25 tools across analysis, navigation, refactoring, and search categories.
- **Added:** Stage 3 backends — Jedi, Rope, and Pyright integration with shared type and reference infrastructure.
- **Added:** Stage 4 tool orchestration layer and initial test surface.
- **Added:** Stage 6 packaging polish — PyInstaller bundle, `build.bat` wrapper, PE timestamp fix, Pyright startup hardening.
- **Added:** Python 3.14 minimum, CI workflow (lint + Pyright + mypy + unit + integration on Windows), and ergonomics docs.
- **Added:** SRP refactoring pass — decomposed god modules into focused packages.
- **Added:** MCP directory compliance — tool annotations, privacy policy, manifest.
- **Added:** Wave-2 tool surface, hardening, integration coverage.
- **Added:** P0/P1 backlog items — security, hardening, usability, performance (#13).

[Unreleased]: https://github.com/darylmcd/Jedi-Py-MCP/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/darylmcd/Jedi-Py-MCP/releases/tag/v0.4.1
