# P0-P3 Implementation Plan — Findings & Wave-Based Approach

Generated 2026-03-27 from end-to-end MCP server analysis of its own codebase
and an external project (CLI-Inventory-Tool). Covers 22 backlog items across
P0 (bug fixes) through P3 (advanced analysis features).

---

## Codebase Architecture Summary

The server has 3 backends composed into `AppContext` at startup:
- **PyrightLSPClient** (`backends/pyright_lsp.py`, 1448 lines) — LSP-based type-aware analysis
- **JediBackend** (`backends/jedi_backend.py`, 370 lines) — dynamic fallback analysis
- **RopeBackend** (`backends/rope_backend.py`, 597 lines) — mutation-safe refactoring

Tools are registered via `@mcp.tool()` in `server.py` (952 lines, 53 functions),
which delegates to orchestration functions in `tools/{analysis,navigation,refactoring,search,composite}.py`.
All data structures are Pydantic models in `models.py` (293 lines).
Config is in `config.py` with `workspace_root` fixed at startup via CLI arg.

**Dependencies**: mcp>=1.20, pydantic>=2.0, jedi>=0.19, rope>=1.13, pyright>=1.1.380, libcst>=1.1
**NOT available** (not adding): radon, vulture, bandit, import-linter, grimp, ast-grep

All new features use Python stdlib `ast` (already used in `tools/search.py`), existing `libcst`, and existing backends.

---

## Wave 1: P0 Bug Fixes (6 items)

Foundation fixes that later items depend on.

### 1.1 Workspace scoping: `get_workspace_diagnostics` + `dead_code_detection`

**Problem**: Workspace-scoped tools iterate `config.workspace_root` which may
point to the MCP server's own directory, not the target project. Confirmed in
two independent sessions.

**Root cause**: `workspace_root` is set at server startup via CLI arg in
`__main__.py` and stored as `_workspace_root` global in `server.py:115`.
When the MCP server is configured with a hardcoded arg pointing at its own
directory, all workspace-scoped file iterations (`_python_files(config.workspace_root)`)
scope incorrectly.

**Fix**: Add optional `root_path: str | None = None` parameter to
workspace-iterating tools. When provided, resolve it and use instead of
`config.workspace_root` for `_python_files()`.

**Files to change**:
- `tools/analysis.py:427` — `get_workspace_diagnostics()`: add `root_path` param
- `tools/search.py:475` — `dead_code_detection()`: add `root_path` param at line 482
- `tools/navigation.py:323` — `get_symbol_outline()` (workspace mode): add `root_path` param
- `server.py` — update 3 tool registrations to pass through `root_path`

**Implementation detail**: In each function, before file iteration:
```python
effective_root = Path(root_path).resolve() if root_path else config.workspace_root
target_files = [Path(file_path).resolve()] if file_path else _python_files(effective_root)
```

---

### 1.2 `type_hierarchy` empty results

**Problem**: `prepare_type_hierarchy` returns empty when cursor isn't on the
class name token. At `navigation.py:258-271`, empty roots produce a placeholder
with `name=""`. Confirmed for `PyrightLSPClient`, `JediBackend`, `RopeBackend`,
and `ConfigError(Exception)`.

**Root cause**: The Pyright LSP `textDocument/prepareTypeHierarchy` method requires
the cursor to be exactly on the class name identifier. If the cursor is on the
`class` keyword or elsewhere on the line, it returns `null`.

**Fix**: When `roots` is empty, use `ast.parse` to find the class definition
at/near the given line, extract the exact column offset of the class name token,
and retry. Add optional `class_name: str | None` parameter for direct lookup.

**Files to change**:
- `tools/navigation.py:241-271` — `type_hierarchy()`: add `class_name` param
  and AST-based position resolution when roots are empty
- `server.py:422` — update registration to pass `class_name`

**Implementation detail**: After line 258 (`roots = await pyright.prepare_type_hierarchy(...)`):
```python
if not roots:
    # Retry: find exact class name position via AST
    resolved = _resolve_class_position(file_path, line, character, class_name)
    if resolved and (resolved[0] != line or resolved[1] != character):
        roots = await pyright.prepare_type_hierarchy(file_path, resolved[0], resolved[1])
```

Helper `_resolve_class_position(file_path, line, char, class_name)` parses with
`ast`, walks `module.body` for `ast.ClassDef` nodes, and returns `(lineno-1, col_offset + len("class "))`.

---

### 1.3 `get_folding_ranges` empty results

**Problem**: Pyright returns `[]` or doesn't support `textDocument/foldingRange`.
The `_is_unhandled_method_error` check at `pyright_lsp.py:1225` silently returns `[]`.
No fallback exists. Confirmed on files with 500-700+ lines.

**Fix**: Add AST-based fallback in the navigation tool layer. When Pyright returns
empty, parse the file with `ast` and generate `FoldingRange` entries from compound
statement nodes.

**Files to change**:
- `tools/navigation.py` — add `_ast_folding_ranges(file_path: str) -> list[FoldingRange]`
  helper; modify `get_folding_ranges()` (currently a thin Pyright delegation) to
  call fallback when result is empty

**Implementation detail**: The helper walks `ast.parse(source).body` recursively
and creates `FoldingRange(start_line=node.lineno-1, end_line=node.end_lineno-1, kind="region")`
for `FunctionDef`, `AsyncFunctionDef`, `ClassDef`, `If`, `For`, `While`, `With`,
`Try`, and consecutive import groups.

---

### 1.4 `organize_imports` silent no-op error

**Problem**: `_pick_code_action()` at `refactoring.py:317-318` raises
`ValueError("No code actions were available...")` when imports are already
optimal. Users cannot distinguish "nothing to change" from "tool broken."
Confirmed on 6/6 files tested.

**Root cause**: `organize_imports()` at line 522-523 calls `_pick_code_action(organize_actions, ...)`
which raises when `actions` list is empty. The function doesn't differentiate
between "no changes needed" and "tool failure."

**Fix**: In `organize_imports()` at `refactoring.py:504-528`, check
`if not organize_actions:` before calling `_pick_code_action` and return a
success result with empty edits. Also handle the empty-edits case at line 525-526.

**Files to change**:
- `tools/refactoring.py:504-528` — add two early-return guards

**Implementation detail**: Before line 523:
```python
if not organize_actions:
    return RefactorResult(
        edits=[], files_affected=[], description="Imports already organized",
        applied=False, diagnostics_after=[],
    )
```
Replace lines 525-526 (the "no editable workspace changes" error) with the same pattern.

---

### 1.5 `get_symbol_outline` empty children

**Problem**: `get_document_symbols()` at `pyright_lsp.py:384` handles both
`DocumentSymbol[]` (hierarchical, has `children` and `range`) and
`SymbolInformation[]` (flat, has `location` and `containerName`). The code at
lines 402-446 processes children recursively, but when Pyright returns the flat
format, each entry has `containerName` set and no `children` array. The code
correctly reads `containerName` at line 437 but doesn't reconstruct the hierarchy.

**Fix**: After converting all entries at lines 449-456, if the result is flat
(entries have `container` set but no children), reconstruct hierarchy by matching
entries to their parent by `container` name.

**Files to change**:
- `backends/pyright_lsp.py:449-456` — add post-conversion hierarchy reconstruction

**Implementation detail**: After the conversion loop:
```python
# Reconstruct hierarchy from flat SymbolInformation format
by_name: dict[str, SymbolOutlineItem] = {s.name: s for s in symbols}
orphans: list[SymbolOutlineItem] = []
for sym in list(symbols):
    if sym.container and sym.container in by_name:
        parent = by_name[sym.container]
        parent.children.append(sym)
    else:
        orphans.append(sym)
if any(s.children for s in symbols):
    symbols = [s for s in symbols if s.container is None or s.container not in by_name]
```

---

### 1.6 `call_hierarchy` decorator traversal

**Problem**: When `prepareCallHierarchy` resolves to a decorator, outgoing calls
are the decorator's internals. Confirmed: `app_lifespan` (decorated with
`@asynccontextmanager`) resolved to `contextlib.py` instead of function body callees.

**Fix**: In `tools/navigation.py:call_hierarchy()`, after getting roots, detect
if the root resolves to a stdlib/site-packages path. If so, use `ast` to find
the decorated function's `def` line and retry.

**Files to change**:
- `tools/navigation.py:192` — add decorator detection after getting roots

**Implementation detail**: Check if `root.file_path` contains `site-packages` or
known stdlib paths (`contextlib.py`, `functools.py`). If so, parse the original
file with `ast`, find the `FunctionDef` at the given line (accounting for
decorator lines), compute the position of the `def` keyword, and retry
`prepare_call_hierarchy` at that position.

---

## Wave 2: P1 Usability Enhancements (6 items)

Depends on Wave 1 for workspace scoping fix.

### 2.1 `structural_search` pattern usability

**Problem**: `eval(pattern, {}, {"m": m, "cst": cst})` at `search.py:422` requires
raw LibCST matcher DSL. All 5 natural-language patterns attempted failed.
Error message at line 424 says only "Invalid LibCST matcher pattern." with no guidance.

**Fix**: Add `_translate_simplified_pattern(pattern: str) -> str | None` that
converts common shorthand patterns to LibCST matcher expressions. Try translation
first; fall back to raw eval. Enhance error message with examples.

**Simplified pattern mappings**:
| User pattern | Translated LibCST |
|---|---|
| `except Exception` | `m.ExceptHandler(type=m.Name("Exception"))` |
| `bare except` | `m.ExceptHandler(type=None)` |
| `from X import *` | `m.ImportFrom(names=m.ImportStar())` |
| `import *` | `m.ImportFrom(names=m.ImportStar())` |
| `assert ...` | `m.Assert()` |
| `global X` | `m.Global()` |
| `pass` | `m.Pass()` |

**Files to change**:
- `tools/search.py:410-426` — add `_translate_simplified_pattern()`, update
  `structural_search()` to try translation first, enhance error message

**Error message enhancement**:
```
Invalid pattern. Use LibCST matcher syntax, e.g.:
  m.Call(func=m.Name("foo"))          — find calls to foo()
  m.ExceptHandler(type=m.Name("Exception"))  — find except Exception
  m.ImportFrom(names=m.ImportStar())  — find star imports
  m.Assert()                          — find assert statements
  m.Name("my_var")                    — find name references
```

---

### 2.2 Diagnostic suppression

**Fix**: Add `suppress_codes: list[str] | None = None` parameter to
`get_diagnostics()` and `get_workspace_diagnostics()`. Filter diagnostics
where `diagnostic.code` is in the suppress set.

**Files to change**:
- `tools/analysis.py:389` — `get_diagnostics()`: add param, filter before return
- `tools/analysis.py:427` — `get_workspace_diagnostics()`: add param, pass through
- `server.py` — update 2 registrations

---

### 2.3 Dead code confidence scoring

**Fix**: Add `confidence: str = "medium"` to `DeadCodeItem`. Add
`exclude_test_files: bool = True` parameter to `dead_code_detection()`.
Implement confidence heuristics.

**Confidence rules**:
- `name` matches `logger` or `_LOGGER` → `"low"`
- `name` starts with `test_` → `"low"`
- `name` is in `__all__` (parse from AST) → `"low"`
- `name` is a dunder method → `"low"`
- `kind == "variable"` and name is ALL_CAPS → `"low"` (likely constant)
- `reason == "unused diagnostic"` → `"high"`
- All others → `"medium"`

**Files to change**:
- `models.py` — add `confidence: str = "medium"` to `DeadCodeItem`
- `tools/search.py:475-547` — implement scoring after item creation, add
  `exclude_test_files` filter
- `server.py` — update registration

---

### 2.4 Result pagination

**Fix**: Add `offset: int = 0` to workspace-wide tools. Return wrapper models
with `total_count` and `truncated`.

**New models in `models.py`**:
```python
class DeadCodeResult(BaseModel):
    items: list[DeadCodeItem]
    total_count: int
    truncated: bool = False

class WorkspaceDiagnosticsResult(BaseModel):
    summaries: list[DiagnosticSummary]
    total_count: int
    truncated: bool = False
```

**Files to change**:
- `models.py` — add 2 wrapper models
- `tools/analysis.py` — `get_workspace_diagnostics()` returns `WorkspaceDiagnosticsResult`
- `tools/search.py` — `dead_code_detection()` returns `DeadCodeResult`
- `tools/navigation.py` — `get_symbol_outline()` add `offset` param
- `server.py` — update registrations

**Note**: This changes return types for `dead_code_detection` and
`get_workspace_diagnostics`. Callers will need to access `.items` / `.summaries`.

---

### 2.5 Batch/multi-file operations

**Fix**: Add `file_paths: list[str] | None = None` parameter to 4 tools.
When provided, iterate and aggregate. Mutually exclusive with single `file_path`.

**Files to change**:
- `tools/analysis.py` — `get_diagnostics()`: add `file_paths`
- `tools/search.py` — `dead_code_detection()`: add `file_paths`
- `tools/refactoring.py` — `organize_imports()`: add `file_paths`
- `tools/navigation.py` — `get_symbol_outline()`: add `file_paths`
- `server.py` — update 4 registrations

**Validation**: Raise `ValueError` if both `file_path` and `file_paths` are provided.

---

### 2.6 Rename diff preview

**Fix**: Add `include_diff: bool = False` to `rename_symbol()`. When true and
`apply=False`, compute unified diffs using existing `build_unified_diff()` from
`util/diff.py`. Add `diffs: list[DiffPreview] | None = None` to `RefactorResult`.

**Files to change**:
- `models.py` — add `diffs: list[DiffPreview] | None = None` to `RefactorResult`
- `tools/refactoring.py:382` — `rename_symbol()`: add `include_diff` param,
  after getting edits group by file and call `build_unified_diff()`
- `server.py` — update registration

---

## Wave 3: P2 New Tools — Metrics & Dependencies (2 items)

These create the new `tools/metrics.py` module that Waves 4-5 build on.

### 3.1 `code_metrics` tool

**New file**: `src/python_refactor_mcp/tools/metrics.py`

Use Python `ast` module (already used in `tools/search.py`) to compute
per-function metrics. No new dependency needed.

**Algorithm**:
- **Cyclomatic complexity**: Count decision points per function:
  `If`, `IfExp`, `For`, `While`, `ExceptHandler`, `With`, `Assert`,
  `BoolOp(And)`, `BoolOp(Or)`, `comprehension` → +1 each, base = 1
- **Cognitive complexity**: Increment per nesting level for branches.
  Each nested `if/for/while/try` adds `nesting_level + 1` instead of flat `+1`.
- **Nesting depth**: Track max depth during AST walk
- **LoC**: `node.end_lineno - node.lineno + 1`
- **Parameter count**: `len(args.args) + len(args.posonlyargs) + len(args.kwonlyargs) + (1 if args.vararg else 0) + (1 if args.kwarg else 0)`

Supports `file_path`, `file_paths`, `root_path`, and `limit` parameters.

**New models in `models.py`**:
```python
class FunctionMetrics(BaseModel):
    name: str
    kind: str  # "function" | "method"
    file_path: str
    range: Range
    line_count: int
    cyclomatic_complexity: int
    cognitive_complexity: int
    max_nesting_depth: int
    parameter_count: int
    container: str | None = None

class CodeMetricsResult(BaseModel):
    functions: list[FunctionMetrics]
    total_count: int
    truncated: bool = False
```

**Files**:
- `tools/metrics.py` — **new**: `code_metrics()`, complexity visitors
- `models.py` — add 2 models
- `server.py` — register `code_metrics` tool
- `tests/unit/test_metrics_tools.py` — **new**: tests with known-complexity functions

---

### 3.2 `get_module_dependencies` tool

Parse imports via `ast.Import`/`ast.ImportFrom` nodes. Resolve module names to
file paths relative to workspace root where possible. Build directed adjacency
list. Detect cycles via DFS with 3-color marking (white/gray/black).

**New models in `models.py`**:
```python
class DependencyEdge(BaseModel):
    source: str  # file path of importer
    target: str  # file path of imported module (or module name if unresolvable)
    import_name: str  # the import string as written

class CircularDependency(BaseModel):
    cycle: list[str]  # ordered file paths forming the cycle

class ModuleDependencyResult(BaseModel):
    edges: list[DependencyEdge]
    circular_dependencies: list[CircularDependency]
    module_count: int
```

**Files**:
- `tools/metrics.py` — add `get_module_dependencies()`, `_resolve_import_to_path()`,
  `_detect_cycles()`, `_build_import_graph()`
- `models.py` — add 3 models
- `server.py` — register tool
- `tests/unit/test_metrics_tools.py` — add tests with circular and acyclic imports

---

## Wave 4: P2 New Tools — Search & Coverage (3 items)

### 4.1 `find_unused_imports` tool

**Primary strategy**: Use Pyright diagnostics filtered for `reportUnusedImport` code.
**Fallback**: Parse with `ast`, extract all import names, walk file body with
`ast.walk()` checking `ast.Name` nodes for usage.

**New model**: `UnusedImport(name: str, file_path: str, range: Range, import_statement: str)`

**Files**:
- `tools/search.py` — add `find_unused_imports(pyright, config, file_path, file_paths, root_path)`
- `models.py` — add `UnusedImport` model
- `server.py` — register tool
- `tests/unit/test_search_tools.py` — add tests

---

### 4.2 `find_duplicated_code` tool

Use `ast.dump(node, annotate_fields=False)` to normalize function/method bodies.
Hash each body with `hashlib.md5`. Group functions with identical hashes ("exact"
duplicates). For "structural" duplicates, replace all `ast.Name.id` with a
placeholder string before dumping, then hash.

Accept `min_lines: int = 5` to filter out trivial functions.

**New models in `models.py`**:
```python
class DuplicateItem(BaseModel):
    name: str
    kind: str
    file_path: str
    range: Range
    line_count: int

class DuplicateGroup(BaseModel):
    hash: str
    items: list[DuplicateItem]
    similarity: str  # "exact" | "structural"

class DuplicateCodeResult(BaseModel):
    groups: list[DuplicateGroup]
    total_duplicates: int
```

**Files**:
- `tools/metrics.py` — add `find_duplicated_code(config, file_path, file_paths, root_path, min_lines, limit)`
- `models.py` — add 3 models
- `server.py` — register tool
- `tests/unit/test_metrics_tools.py` — add tests with known-duplicate functions

---

### 4.3 `get_type_coverage` tool

Walk AST function definitions. For each, check:
- Return annotation: `node.returns is not None`
- Each parameter: `arg.annotation is not None` for all arg lists
- Compute percentages and list unannotated symbols.

**New models in `models.py`**:
```python
class UnannotatedSymbol(BaseModel):
    name: str
    kind: str  # "parameter" | "return"
    file_path: str
    line: int
    function_name: str

class TypeCoverageResult(BaseModel):
    total_functions: int
    functions_with_return_annotation: int
    total_parameters: int
    annotated_parameters: int
    return_annotation_pct: float
    parameter_annotation_pct: float
    unannotated: list[UnannotatedSymbol]
    truncated: bool = False
```

**Files**:
- `tools/metrics.py` — add `get_type_coverage(config, file_path, file_paths, root_path, limit)`
- `models.py` — add 2 models
- `server.py` — register tool
- `tests/unit/test_metrics_tools.py` — add tests

---

## Wave 5: P3 Advanced Analysis (5 items)

These depend on the module dependency graph from Wave 3.

### 5.1 `get_coupling_metrics` tool

Reuse `_build_import_graph()` from `get_module_dependencies` internally.
For each module compute:
- **Ca** (afferent coupling): number of modules that import this module
- **Ce** (efferent coupling): number of modules this module imports
- **Instability**: I = Ce / (Ca + Ce) — 0 = fully stable, 1 = fully unstable

**New models**: `ModuleCouplingMetrics(file_path, afferent_coupling, efferent_coupling, instability)`, `CouplingResult(modules)`

**Files**: `tools/metrics.py`, `models.py`, `server.py`, tests

---

### 5.2 `check_layer_violations` tool

Accept `layers: list[list[str]]` — ordered list of module groups from highest
to lowest layer. Each group is a list of module path globs (e.g.,
`["src/models.py"]`, `["src/config*.py"]`, `["src/ssh*.py"]`).

Walk the import graph. For each edge, determine source and target layers.
Flag edges that go from a lower layer index to a higher (lower number) layer index.

**New models**: `LayerViolation(source_file, target_file, import_name, source_layer, target_layer)`, `LayerViolationResult(violations, total_violations)`

**Files**: `tools/metrics.py`, `models.py`, `server.py`, tests

---

### 5.3 `interface_conformance` tool

Given `class_names: list[str]` and optional `file_path` hints, use `ast` to
extract method signatures for each class (name, parameter names, return
annotation text). Compare across classes for:
- **Common methods**: same name in all classes
- **Unique methods**: present in only one class
- **Signature mismatches**: same name but different parameter counts/types

**New models**: `MethodSignature(name, parameters, return_annotation, file_path, line)`,
`InterfaceConformanceResult(classes, common_methods, unique_methods, mismatches)`

**Files**: `tools/metrics.py`, `models.py`, `server.py`, tests

---

### 5.4 `extract_protocol` tool

Reuse `interface_conformance` logic to find common methods. Generate a Protocol
class source string using `ast.unparse()` on constructed AST nodes, or string
formatting for the Protocol body.

**New model**: `ExtractProtocolResult(protocol_name, source_code, methods, based_on_classes)`

**Files**: `tools/metrics.py`, `models.py`, `server.py`, tests

---

### 5.5 `get_module_public_api` tool

Thin wrapper over `get_symbol_outline`. Filter results to exclude names starting
with `_`. If `__all__` exists in the module (detected by parsing AST), restrict
to those names only.

No new models needed — reuses `list[SymbolOutlineItem]`.

**Files**:
- `tools/navigation.py` — add `get_module_public_api(pyright, file_path)`
- `server.py` — register tool
- `tests/unit/test_navigation_tools.py` — add tests

---

## File Change Summary

| File | Waves | Description |
|---|---|---|
| `tools/metrics.py` | 3,4,5 | **New file**: 8 tool functions (code_metrics, module_dependencies, duplicated_code, type_coverage, coupling_metrics, layer_violations, interface_conformance, extract_protocol) |
| `models.py` | 2,3,4,5 | ~15 new Pydantic model classes |
| `server.py` | 1-5 | Update ~10 existing registrations + ~9 new tool registrations |
| `tools/analysis.py` | 1,2 | `root_path`, `suppress_codes`, `file_paths`, pagination wrapper |
| `tools/navigation.py` | 1,2,5 | `root_path`, AST folding fallback, type_hierarchy fix, decorator fix, `get_module_public_api` |
| `tools/refactoring.py` | 1,2 | organize_imports fix, rename diff, batch organize_imports |
| `tools/search.py` | 1,2,4 | Workspace scoping, structural_search UX, dead code confidence, `find_unused_imports` |
| `backends/pyright_lsp.py` | 1 | Symbol outline hierarchy reconstruction from flat SymbolInformation |
| `tests/unit/test_metrics_tools.py` | 3,4,5 | **New file**: all metrics/analysis tool tests |
| Existing `tests/unit/test_*.py` | 1,2 | Additional test cases per fix/enhancement |

---

## Wave Dependencies

```
Wave 1 (P0 bugs)        Items 1.1-1.6    No dependencies
  │
Wave 2 (P1 usability)   Items 2.1-2.6    Depends on 1.1 (workspace scoping)
  │
Wave 3 (P2 part 1)      Items 3.1-3.2    New tools/metrics.py module
  │
Wave 4 (P2 part 2)      Items 4.1-4.3    4.2-4.3 go in metrics.py; 4.1 in search.py
  │
Wave 5 (P3 advanced)    Items 5.1-5.5    5.1-5.2 depend on 3.2 (dep graph)
                                          5.3-5.4 depend on each other
                                          5.5 is independent
```

---

## Verification Plan

**After each wave**:
1. `python -m ruff check .` — lint clean
2. `python -m pyright .` — type check clean
3. `python -m pytest tests/unit/ -v` — all unit tests pass

**After all waves**:
4. `./scripts/test-integration.ps1` with `RUN_MCP_INTEGRATION=1`
5. Re-run the self-analysis to confirm P0 fixes (workspace scoping, type hierarchy,
   folding ranges, organize_imports, symbol outline children, call hierarchy decorators)
6. Run against an external project (e.g., `CLI-Inventory-Tool`) to verify
   cross-project scoping and new tools work on non-trivial codebases
7. Test new tools (code_metrics, module_dependencies, etc.) on the MCP server's
   own codebase and verify results are reasonable
