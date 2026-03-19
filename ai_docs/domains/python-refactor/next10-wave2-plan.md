# Next-10 Wave 2 — Implementation Plan

Purpose: implementation plan for the next 10 new MCP tools plus enhancements to existing tools.
Status: **Draft — awaiting approval**.

---

## Part A — Existing Tool Enhancements

Improvements to the current 35-tool surface that increase agent autonomy,
reduce round-trips, and harden edge cases.

### A1. `find_references` — add source-line context (Medium)

**Problem:** Returns `Location` objects (file + range) but not the source text,
forcing the agent to make separate `read_file` calls for every reference.

**Change:**
- Add an optional `include_context: bool = False` parameter.
- When true, read each referenced line and include it as a `context` string
  field on each location in the result.
- Cap context to 1 line per reference to keep payloads bounded.

**Files:** `models.py` (add field), `tools/analysis.py`, unit tests.

### A2. `call_hierarchy` — add max-items guard (High)

**Problem:** Large call graphs (common utility helpers) can produce unbounded
result sets that exceed MCP response limits.

**Change:**
- Add `max_items: int = 200` parameter.
- Stop traversal once the item budget is exhausted and set a
  `truncated: bool` flag on the result.

**Files:** `tools/navigation.py`, `models.py`, unit tests.

### A3. `get_symbol_outline` — add kind/name filtering (High)

**Problem:** Workspace-wide symbol outlines return thousands of entries with no
way to filter, making the result too large for the agent to use effectively.

**Change:**
- Add optional `kind_filter: list[str] | None = None` (e.g. `["class", "function"]`).
- Add optional `name_pattern: str | None = None` (regex match on symbol name).
- Apply filters before serialization.

**Files:** `tools/navigation.py`, unit tests.

### A4. `smart_rename` / `rename_symbol` — integrate `prepare_rename` preflight (Medium)

**Problem:** `rename_symbol` and `smart_rename` call Rope directly without
verifying the symbol is renameable, producing confusing Rope errors for
non-renameable positions (keywords, string literals, etc.).

**Change:**
- Both tools call `prepare_rename` internally before executing.
- If preflight fails, return an actionable `isError` response immediately
  instead of forwarding a cryptic Rope exception.

**Files:** `tools/refactoring.py`, `tools/composite.py`, unit tests.

### A5. `extract_method` — expose `similar` parameter (Medium)

**Problem:** Rope's `ExtractMethod` supports a `similar=True` flag to find and
replace all occurrences of the same code pattern, but the tool hardcodes this
off.

**Change:**
- Add `similar: bool = False` parameter to the tool.
- Pass through to `rope.extract_method`.

**Files:** `tools/refactoring.py`, `backends/rope_backend.py`, unit tests.

### A6. `dead_code_detection` — use Pyright diagnostic tags (Medium)

**Problem:** Relies on string-matching diagnostic messages ("unused",
"not accessed") instead of checking the standard LSP `DiagnosticTag.Unnecessary`
tag, causing false negatives when message wording changes.

**Change:**
- Check `diagnostic.tags` for the `Unnecessary` (1) tag.
- Keep the string-match as a secondary fallback.
- Also add an `exclude_patterns: list[str] | None` parameter for
  user-defined exclusions (e.g., entry-point files).

**Files:** `tools/search.py`, `models.py` (tag field), unit tests.

### A7. Global `limit` parameter pattern (Medium)

**Problem:** No list-returning tool supports pagination or bounded result sets.
Enterprise-scale repos can produce oversized responses.

**Change:**
- Add `limit: int | None = None` to all list-returning tools:
  `find_references`, `get_completions`, `search_symbols`, `structural_search`,
  `get_diagnostics`, `find_constructors`.
- When set, truncate results and include a `truncated` flag.
- Default: `None` (no limit) to preserve backward compatibility.

**Files:** All tool modules, `models.py`, unit tests for truncation behavior.

---

## Part B — New Tools (10)

Ordered by priority score (agent utility + safety + complexity + testability +
chainability). Each tool follows the intake checklist from `mcp-checklist.md`.

### Wave I — Signature & Hierarchy (Tools 1–2)

#### B1. `change_signature` — Rope (Priority Score: 23/25)

**Purpose:** Add, remove, reorder, or rename function parameters and
automatically update all call sites.

**Backend:** `rope.refactor.change_signature.ChangeSignature`

**Args:**
| Param | Type | Required | Description |
|---|---|---|---|
| `file_path` | `str` | yes | File containing the function. |
| `line` | `int` | yes | Line of function definition. |
| `character` | `int` | yes | Column within function signature. |
| `operations` | `list[SignatureOp]` | yes | Ordered list of add/remove/reorder/rename/inline_default/normalize ops. |
| `apply` | `bool` | no | Default `False` (preview). |

**SignatureOp union:**
- `{"op": "add", "index": int, "name": str, "default": str | None}`
- `{"op": "remove", "index": int}`
- `{"op": "reorder", "new_order": list[int]}`
- `{"op": "rename", "index": int, "new_name": str}`
- `{"op": "inline_default", "index": int}`
- `{"op": "normalize"}`

**Returns:** `RefactorResult`

**Agent value:** Most-requested refactoring after rename. Every API evolution
task involves parameter changes.

**Rope backend method to add:** `change_signature(resource, offset, operations)`

#### B2. `type_hierarchy` — Pyright (Priority Score: 22/25)

**Purpose:** Navigate class inheritance — supertypes and subtypes.

**Backend:** Pyright LSP `textDocument/prepareTypeHierarchy` +
`typeHierarchy/supertypes` + `typeHierarchy/subtypes`

**Args:**
| Param | Type | Required | Description |
|---|---|---|---|
| `file_path` | `str` | yes | File containing the class/type. |
| `line` | `int` | yes | Line of the symbol. |
| `character` | `int` | yes | Column of the symbol. |
| `direction` | `str` | no | `"supertypes"`, `"subtypes"`, or `"both"` (default `"both"`). |
| `depth` | `int` | no | Max traversal depth (default `3`). |

**Returns:** `TypeHierarchyResult` — tree of `TypeHierarchyItem` nodes with
name, kind, file, range, and children.

**Pyright backend methods to add:**
- `prepare_type_hierarchy(file_path, line, character)`
- `get_supertypes(item)`
- `get_subtypes(item)`

**Agent value:** Essential for understanding OOP code — currently the only
class navigation missing alongside `call_hierarchy`.

### Wave J — Pattern Transformation (Tools 3–4)

#### B3. `restructure` (structural replace) — Rope (Priority Score: 21/25)

**Purpose:** Pattern-based automated code transformation. The "write" half of
`structural_search`.

**Backend:** `rope.refactor.restructure.Restructure`

**Args:**
| Param | Type | Required | Description |
|---|---|---|---|
| `pattern` | `str` | yes | Rope pattern to match (e.g., `"${x}.has_key(${y})"`). |
| `goal` | `str` | yes | Replacement pattern (e.g., `"${y} in ${x}"`). |
| `checks` | `dict[str, str]` | no | Type constraint checks on pattern vars. |
| `imports` | `list[str]` | no | Imports to add if the replacement introduces new names. |
| `file_path` | `str` | no | Restrict to a single file; `None` → workspace-wide. |
| `apply` | `bool` | no | Default `False` (preview). |

**Returns:** `RefactorResult`

**Agent value:** Enables bulk migration patterns (API upgrades, deprecation
replacement) that agents frequently need.

**Rope backend method to add:** `restructure(pattern, goal, checks, imports, file_path)`

#### B4. `use_function` — Rope (Priority Score: 20/25)

**Purpose:** Find duplicated code matching a function's body and replace with
calls to that function — automated DRY cleanup.

**Backend:** `rope.refactor.usefunction.UseFunction`

**Args:**
| Param | Type | Required | Description |
|---|---|---|---|
| `file_path` | `str` | yes | File containing the target function. |
| `line` | `int` | yes | Line of the function. |
| `character` | `int` | yes | Column within the function name. |
| `apply` | `bool` | no | Default `False` (preview). |

**Returns:** `RefactorResult`

**Agent value:** Agents regularly identify duplicated logic. This lets them
replace it automatically instead of manual editing.

**Rope backend method to add:** `use_function(resource, offset)`

### Wave K — Design Pattern Refactoring (Tools 5–6)

#### B5. `introduce_factory` — Rope (Priority Score: 19/25)

**Purpose:** Replace direct constructor calls with a factory method, improving
testability and enabling dependency injection.

**Backend:** `rope.refactor.introduce_factory.IntroduceFactory`

**Args:**
| Param | Type | Required | Description |
|---|---|---|---|
| `file_path` | `str` | yes | File containing the class. |
| `line` | `int` | yes | Line of the class definition. |
| `character` | `int` | yes | Column within the class name. |
| `factory_name` | `str` | no | Name for the factory function (default: `"create_<classname>"`). |
| `global_factory` | `bool` | no | If `True`, create module-level function; if `False`, static method (default `True`). |
| `apply` | `bool` | no | Default `False` (preview). |

**Returns:** `RefactorResult`

**Agent value:** Classic design-pattern refactoring that agents recommend but
currently cannot apply automatically.

**Rope backend method to add:** `introduce_factory(resource, offset, factory_name, global_factory)`

#### B6. `get_documentation` — Jedi (Priority Score: 19/25)

**Purpose:** Full rendered docstrings and API help for any symbol. Complements
`get_hover_info` (which focuses on type signatures).

**Backend:** `jedi.Script.help()`

**Args:**
| Param | Type | Required | Description |
|---|---|---|---|
| `file_path` | `str` | yes | File path. |
| `line` | `int` | yes | Cursor line. |
| `character` | `int` | yes | Cursor column. |
| `source` | `str` | no | Override file content (for unsaved buffers). |

**Returns:** `DocumentationResult` — list of `DocEntry` objects with `name`,
`module_path`, `type`, `full_doc`, `signatures`.

**Jedi backend method to add:** `get_help(source, file_path, line, character)`

**Agent value:** Agents need to read full API docs in-context. Hover gives
short type summaries; this gives the complete docstring including parameters,
returns, raises, and examples sections.

### Wave L — Structural Module Refactoring (Tools 7–8)

#### B7. `module_to_package` — Rope (Priority Score: 18/25)

**Purpose:** Convert a single `.py` module into a `package/__init__.py`
directory, preserving all imports.

**Backend:** `rope.refactor.topackage.ModuleToPackage`

**Args:**
| Param | Type | Required | Description |
|---|---|---|---|
| `file_path` | `str` | yes | The module file to convert. |
| `apply` | `bool` | no | Default `False` (preview). |

**Returns:** `RefactorResult`

**Agent value:** Essential when agents decompose growing modules into
sub-packages.

**Rope backend method to add:** `module_to_package(resource)`

#### B8. `local_to_field` — Rope (Priority Score: 17/25)

**Purpose:** Promote a local variable inside a method to a class instance
attribute (`self.x`).

**Backend:** `rope.refactor.localtofield.LocalToField`

**Args:**
| Param | Type | Required | Description |
|---|---|---|---|
| `file_path` | `str` | yes | File containing the method. |
| `line` | `int` | yes | Line of the local variable. |
| `character` | `int` | yes | Column of the variable name. |
| `apply` | `bool` | no | Default `False` (preview). |

**Returns:** `RefactorResult`

**Agent value:** Common when refactoring state management — agents cache
intermediate results or promote computed values.

**Rope backend method to add:** `local_to_field(resource, offset)`

### Wave M — Advanced Refactoring & Navigation (Tools 9–10)

#### B9. `method_object` — Rope (Priority Score: 16/25)

**Purpose:** Transform a complex method into a callable class. Decomposes
god-methods into single-responsibility objects.

**Backend:** `rope.refactor.method_object.MethodObject`

**Args:**
| Param | Type | Required | Description |
|---|---|---|---|
| `file_path` | `str` | yes | File containing the method. |
| `line` | `int` | yes | Line of the method. |
| `character` | `int` | yes | Column within the method name. |
| `classname` | `str` | no | Name for the new class (default derived from method name). |
| `apply` | `bool` | no | Default `False` (preview). |

**Returns:** `RefactorResult`

**Agent value:** Decomposes complex methods when agents detect high
cyclomatic complexity or too many local variables.

**Rope backend method to add:** `method_object(resource, offset, classname)`

#### B10. `selection_range` — Pyright (Priority Score: 16/25)

**Purpose:** Smart expanding selection at a cursor position — expression →
statement → block → function → class → module.

**Backend:** Pyright LSP `textDocument/selectionRange`

**Args:**
| Param | Type | Required | Description |
|---|---|---|---|
| `file_path` | `str` | yes | Target file. |
| `positions` | `list[Position]` | yes | One or more cursor positions. |

**Returns:** `list[SelectionRangeResult]` — nested range chain from innermost
to outermost scope for each position.

**Pyright backend method to add:** `get_selection_range(file_path, positions)`

**Agent value:** Utility tool that makes extract/inline targets precise —
agents can auto-discover the correct code span instead of guessing line offsets.

---

## Implementation Sequence

### Phase 1 — Hardening (Waves A1–A7)

Improve existing tools before adding new surface area.

| Step | Item | Estimated Scope | Dependencies |
|---|---|---|---|
| 1.1 | A7: Global `limit` pattern | models + all tool modules | None |
| 1.2 | A2: `call_hierarchy` max-items | navigation.py | A7 pattern |
| 1.3 | A3: `get_symbol_outline` filtering | navigation.py | None |
| 1.4 | A1: `find_references` context | analysis.py, models | None |
| 1.5 | A4: Rename preflight integration | refactoring.py, composite.py | None |
| 1.6 | A5: `extract_method` similar | refactoring.py, rope_backend | None |
| 1.7 | A6: `dead_code_detection` tags | search.py, models | None |

### Phase 2 — New Tools (Waves I–M)

One wave at a time; each wave is a merge-ready PR.

| Wave | Tools | Backend Work | Test Work |
|---|---|---|---|
| I | B1 `change_signature`, B2 `type_hierarchy` | rope_backend + pyright_lsp | Unit + integration |
| J | B3 `restructure`, B4 `use_function` | rope_backend | Unit + integration |
| K | B5 `introduce_factory`, B6 `get_documentation` | rope_backend + jedi_backend | Unit + integration |
| L | B7 `module_to_package`, B8 `local_to_field` | rope_backend | Unit + integration |
| M | B9 `method_object`, B10 `selection_range` | rope_backend + pyright_lsp | Unit + integration |

### Per-Wave Deliverables

Each wave PR must include:
1. Backend method(s) in the appropriate backend file.
2. Model classes in `models.py` for new return types.
3. Tool function(s) in the appropriate tool module.
4. Server registration in `server.py`.
5. Unit tests covering happy path, invalid input, and fallback behavior.
6. At least one integration smoke test in `test_end_to_end.py`.
7. Prompt examples added to `mcp-checklist.md`.
8. Reference doc updated in `reference.md`.
9. All validation passes: `ruff check`, `pyright`, `mypy`, `pytest unit`, integration.

---

## Priority Scoring Detail

| # | Tool | Agent Utility | Safety | Complexity | Testability | Chainability | Total |
|---|---|---|---|---|---|---|---|
| B1 | `change_signature` | 5 | 5 | 4 | 5 | 4 | **23** |
| B2 | `type_hierarchy` | 5 | 5 | 4 | 4 | 4 | **22** |
| B3 | `restructure` | 5 | 4 | 4 | 4 | 4 | **21** |
| B4 | `use_function` | 4 | 5 | 4 | 4 | 3 | **20** |
| B5 | `introduce_factory` | 4 | 5 | 4 | 3 | 3 | **19** |
| B6 | `get_documentation` | 4 | 5 | 5 | 3 | 2 | **19** |
| B7 | `module_to_package` | 4 | 4 | 4 | 3 | 3 | **18** |
| B8 | `local_to_field` | 3 | 5 | 4 | 3 | 2 | **17** |
| B9 | `method_object` | 3 | 4 | 4 | 3 | 2 | **16** |
| B10 | `selection_range` | 3 | 5 | 4 | 2 | 2 | **16** |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Rope `ChangeSignature` requires exact offset to function def | B1 breaks on wrong position | Validate with `prepare_rename` or `goto_definition` first |
| Pyright may not advertise `typeHierarchy` provider | B2 unavailable | Check server capabilities at startup; graceful fallback message |
| `Restructure` pattern syntax is Rope-specific | B3 hard for agents to use | Provide 5+ prompt examples with common migration patterns |
| `use_function` may match false positives | B4 applies wrong replacements | Always default to `apply=False`; require explicit opt-in |
| Workspace-wide operations (B3, B4) can be slow | Timeout risk | Add file_path filter and progress feedback |
| `selectionRange` not advertised by all Pyright versions | B10 unavailable | Feature-detect at startup; skip if unsupported |

---

## Open Backlog Items (Carried Forward)

These existing backlog items from `ai_docs/backlog.md` remain open and should
be addressed alongside or after this plan:

- Integration test coverage for `introduce_parameter` and `encapsulate_field`.
- Failure-path integration scenarios (bad line/position, invalid rename).
- Complete prompt example bank for all 35 existing tools.
- Invalid-input unit test coverage for remaining tools.
