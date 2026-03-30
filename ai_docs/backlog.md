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

(All items completed.)

Items resolved in this batch:
- Refactored `get_document_symbols` (CC=24) — extracted `_convert_document_symbol` and `_reconstruct_symbol_hierarchy` to module level.
- Refactored `_build_signature_changers` (cognitive=56) — converted to dispatch table pattern.
- Consolidated `notify_file_changed` — extracted `DiagnosticsNotifier` base protocol in `util/shared.py`.
- Audited `lsp_types.py` — entire file was unused (zero imports), removed.
- `severity_to_string` — confirmed in use internally by `convert_publish_diagnostics`, kept.
- Merged 3 overlapping tool pairs: removed `get_hover_info`, `smart_rename`, `get_call_signatures_fallback` (75 → 72 tools, then +15 new = 87).
- Audited silent error swallowing — added `_LOGGER.debug` to `_snap_to_symbol` in `references.py`.

---

## P3 — Known Limitations

- Status: `documented`
  Area: upstream limitation
  Item: `change_signature` strips Python 3 type annotations during normalization. This is a known rope limitation (`ArgumentNormalizer`). Documented in rope_backend.py docstring.
  Source: mcp-server-audit-report #15 (2026-03-28)

---

## P4 — Stretch / Nice-to-Have

(All items completed.)

Items implemented in this batch (15 new tools):
- **Undo/Redo History** — `undo_refactoring`, `redo_refactoring`, `get_refactoring_history` tools via Rope history.
- **Change Stack** — `begin_change_stack`, `commit_change_stack`, `rollback_change_stack` tools via Rope ChangeStack.
- **Multi-Project Refactoring** — `multi_project_rename` tool via Rope MultiProjectRefactoring.
- **Fuzzy Completion** — added `fuzzy` parameter to `get_completions` tool, delegating to Jedi when fuzzy=True.
- **Project-wide Semantic Search** — `project_search` tool via Jedi Project.search().
- **Keyword/Operator Help** — `get_keyword_help` tool via Jedi Script.help().
- **Simulate Execution** — `simulate_execution` tool via Jedi Name.execute().
- **Sub-definitions** — `get_sub_definitions` tool via Jedi Name.defined_names().
- **Environment Management** — `list_environments` tool via Jedi find_virtualenvs()/find_system_environments().
- **Restart Server** — `restart_server` tool via Pyright restartserver command.
- **Test Coverage Map** — `get_test_coverage_map` tool mapping source symbols to test references.
- **Security Scan** — `security_scan` tool with AST-based SAST rules.

---

## Tests & Documentation

- Status: `open`
  Area: documentation
  Item: Complete prompt example bank coverage for all tools in `ai_docs/domains/python-refactor/mcp-checklist.md`.

Items completed in this batch:
- Integration smoke tests for `introduce_parameter` and `encapsulate_field`.
- Failure-path integration scenarios (invalid position rename, invalid extract range, nonexistent file).
- Invalid-input unit tests (jedi fallback exception, both-backends-fail, rope error propagation, invalid op validation).
