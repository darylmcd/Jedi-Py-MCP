# Changelog

All notable changes to Jedi-Py-MCP will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Category order used in each release: **Fixed** → **Changed — BREAKING** → **Changed** → **Added** → **Maintenance**. Omit empty categories.

## [Unreleased]

### Fixed

### Changed

### Added

### Maintenance

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
