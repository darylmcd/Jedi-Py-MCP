# Python Refactor MCP Server — Agent Implementation Prompt

## Project Overview

Build a **production-grade MCP server** called `python-refactor-mcp` that provides deep Python code analysis and refactoring capabilities by combining three complementary backends:

| Backend | Role | Runtime |
|---|---|---|
| **Pyright** | Type-aware semantic analysis (references, types, diagnostics, call hierarchy) | Node.js subprocess via LSP stdio |
| **Jedi** | Dynamic/runtime-aware analysis fallback (untyped code, metaclasses, Django ORM) | In-process Python library |
| **rope** | Safe refactoring engine (rename, extract, inline, move, structural search) | In-process Python library |

**Key design principle:** Pyright for analysis, Jedi as dynamic fallback, rope for mutation. The MCP server orchestrates all three behind a unified tool surface.

---

## Constraints & Decisions

- **Python 3.13+** (host process and target projects)
- **MCP SDK:** `mcp` PyPI package v1.x (FastMCP high-level API). Use `from mcp.server.fastmcp import FastMCP, Context` patterns.
- **Transport:** `stdio` (default MCP transport). Architecture must NOT block future SSE/Streamable HTTP — use `asyncio` throughout, no blocking I/O on the main thread. The server entry point calls `mcp.run()` which defaults to stdio.
- **Concurrency model:** One MCP server process per client (standard stdio pattern). Internal concurrency via `asyncio` — Pyright LSP is async, rope/jedi operations run via `asyncio.to_thread()` to avoid blocking the event loop.
- **Type safety:** Full type annotations everywhere. `pyright` strict mode (`pyrightconfig.json` with `"typeCheckingMode": "strict"`). `mypy` must also pass clean.
- **File writes:** Tools return `TextEdit[]` diffs by default. Refactoring tools accept an optional `apply: bool = False` parameter — when True, the server writes changes to disk and returns confirmation. When False (default), returns the diffs for the agent to review/apply.
- **Auto-discovery:** Server auto-detects Python environment (venv, pyproject.toml, pyrightconfig.json, setup.cfg) from the workspace root passed at initialization.
- **Packaging:** pip-installable package with `[project.scripts]` console entry point + PyInstaller build target for standalone exe.
- **Testing:** Unit tests with mocked backend responses + integration tests against a fixture Python project.
- **Windows-first:** PowerShell-compatible commands. Avoid bash-specific syntax.

---

## Repository Structure

```
python-refactor-mcp/
├── pyproject.toml
├── pyrightconfig.json
├── README.md
├── AGENTS.md
├── .gitignore
├── scripts/
│   └── build.ps1                        # PyInstaller build script
├── src/
│   └── python_refactor_mcp/
│       ├── __init__.py                   # Package version
│       ├── __main__.py                   # Entry point: python -m python_refactor_mcp
│       ├── server.py                     # FastMCP instance, lifespan, tool registration
│       ├── config.py                     # Server config, env discovery
│       ├── models.py                     # Shared Pydantic models (Position, Range, TextEdit, etc.)
│       ├── backends/
│       │   ├── __init__.py
│       │   ├── pyright_lsp.py            # Pyright subprocess + LSP client
│       │   ├── jedi_backend.py           # Jedi analysis wrapper
│       │   └── rope_backend.py           # rope refactoring wrapper
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── analysis.py              # find_references, get_type_info, get_diagnostics
│       │   ├── navigation.py            # call_hierarchy, goto_definition
│       │   ├── refactoring.py           # rename_symbol, extract_method, extract_variable, inline_variable, move_symbol
│       │   ├── search.py               # find_constructors, structural_search, dead_code_detection, suggest_imports
│       │   └── composite.py            # smart_rename (Pyright refs → rope rename → Pyright validate)
│       └── util/
│           ├── __init__.py
│           ├── lsp_types.py             # LSP protocol types (Position, Range, TextDocumentIdentifier, etc.)
│           ├── lsp_client.py            # Generic async LSP client over stdio
│           └── diff.py                  # Diff generation/application utilities
├── tests/
│   ├── conftest.py                      # Shared fixtures
│   ├── unit/
│   │   ├── test_pyright_lsp.py
│   │   ├── test_jedi_backend.py
│   │   ├── test_rope_backend.py
│   │   ├── test_analysis_tools.py
│   │   ├── test_navigation_tools.py
│   │   ├── test_refactoring_tools.py
│   │   ├── test_search_tools.py
│   │   └── test_composite_tools.py
│   └── integration/
│       ├── conftest.py                  # Fixture project setup
│       ├── test_end_to_end.py
│       └── fixtures/
│           └── sample_project/
│               ├── pyproject.toml
│               ├── src/
│               │   ├── __init__.py
│               │   ├── models.py        # Classes with constructors to find
│               │   ├── service.py       # Functions calling models
│               │   └── utils.py         # Utility functions to extract/inline
│               └── tests/
│                   └── test_models.py
└── .github/
    └── copilot-instructions.md
```

---

## Shared Models (src/python_refactor_mcp/models.py)

All tool inputs/outputs use these Pydantic models for structured MCP responses:

```python
from __future__ import annotations
from pydantic import BaseModel, Field

class Position(BaseModel):
    """0-based line and character offset."""
    line: int
    character: int

class Range(BaseModel):
    start: Position
    end: Position

class Location(BaseModel):
    file_path: str
    range: Range

class TextEdit(BaseModel):
    file_path: str
    range: Range
    new_text: str

class SymbolInfo(BaseModel):
    name: str
    kind: str  # "class", "function", "variable", "method", "module", etc.
    file_path: str
    range: Range
    container: str | None = None  # parent class/function name

class Diagnostic(BaseModel):
    file_path: str
    range: Range
    severity: str  # "error", "warning", "information", "hint"
    message: str
    code: str | None = None

class ReferenceResult(BaseModel):
    symbol: str
    definition: Location | None = None
    references: list[Location]
    total_count: int
    source: str  # "pyright", "jedi", "combined"

class TypeInfo(BaseModel):
    expression: str
    type_string: str
    documentation: str | None = None
    source: str

class CallHierarchyItem(BaseModel):
    name: str
    kind: str
    file_path: str
    range: Range
    detail: str | None = None

class CallHierarchyResult(BaseModel):
    item: CallHierarchyItem
    callers: list[CallHierarchyItem]
    callees: list[CallHierarchyItem]

class RefactorResult(BaseModel):
    edits: list[TextEdit]
    files_affected: list[str]
    description: str
    applied: bool = False  # True if edits were written to disk
    diagnostics_after: list[Diagnostic] | None = None  # Post-refactor validation

class ConstructorSite(BaseModel):
    class_name: str
    file_path: str
    range: Range
    arguments: list[str]  # argument names/expressions at call site

class StructuralMatch(BaseModel):
    file_path: str
    range: Range
    matched_text: str

class DeadCodeItem(BaseModel):
    name: str
    kind: str
    file_path: str
    range: Range
    reason: str  # "no references", "unreachable", etc.

class ImportSuggestion(BaseModel):
    symbol: str
    module: str
    import_statement: str  # e.g. "from collections import OrderedDict"
```

---

## Tool Surface (Complete)

Every tool is registered on the FastMCP instance via `@mcp.tool()` decorators. All tools are async. Parameters use the Pydantic models above for structured output.

### Analysis Tools (tools/analysis.py)

#### `find_references`
```
Parameters:
  file_path: str          # Absolute path to the file
  line: int               # 0-based line number
  character: int          # 0-based character offset
  include_declaration: bool = True
Returns: ReferenceResult
```
- Primary: Pyright `textDocument/references` via LSP
- Fallback: If Pyright returns 0 results or the type is `Unknown`, retry with Jedi `Script.get_references()`
- Merge: Deduplicate by (file_path, line, character)

#### `get_type_info`
```
Parameters:
  file_path: str
  line: int
  character: int
Returns: TypeInfo
```
- Primary: Pyright `textDocument/hover` → extract type from hover markdown
- Fallback: Jedi `Script.infer()` when Pyright returns `Unknown` or no result

#### `get_diagnostics`
```
Parameters:
  file_path: str | None = None  # None = all project files
  severity_filter: str | None = None  # "error", "warning", etc.
Returns: list[Diagnostic]
```
- Source: Pyright diagnostics (collected from LSP `textDocument/publishDiagnostics` notifications)
- Filter by severity if provided
- Sort by file_path, then line

### Navigation Tools (tools/navigation.py)

#### `call_hierarchy`
```
Parameters:
  file_path: str
  line: int
  character: int
  direction: str = "both"  # "callers", "callees", "both"
  depth: int = 1           # How many levels deep
Returns: CallHierarchyResult
```
- Source: Pyright `textDocument/prepareCallHierarchy` → `callHierarchy/incomingCalls` / `callHierarchy/outgoingCalls`

#### `goto_definition`
```
Parameters:
  file_path: str
  line: int
  character: int
Returns: list[Location]
```
- Primary: Pyright `textDocument/definition`
- Fallback: Jedi `Script.goto()` if Pyright returns empty

### Refactoring Tools (tools/refactoring.py)

#### `rename_symbol`
```
Parameters:
  file_path: str
  line: int
  character: int
  new_name: str
  apply: bool = False
Returns: RefactorResult
```
- Engine: rope `Rename` refactoring
- Pre-validation: Pyright `find_references` to enumerate scope
- Post-validation: If `apply=True`, run Pyright diagnostics on affected files and include in result

#### `extract_method`
```
Parameters:
  file_path: str
  start_line: int
  start_character: int
  end_line: int
  end_character: int
  method_name: str
  apply: bool = False
Returns: RefactorResult
```
- Engine: rope `ExtractMethod`

#### `extract_variable`
```
Parameters:
  file_path: str
  start_line: int
  start_character: int
  end_line: int
  end_character: int
  variable_name: str
  apply: bool = False
Returns: RefactorResult
```
- Engine: rope `ExtractVariable`

#### `inline_variable`
```
Parameters:
  file_path: str
  line: int
  character: int
  apply: bool = False
Returns: RefactorResult
```
- Engine: rope `Inline`

#### `move_symbol`
```
Parameters:
  source_file: str
  symbol_name: str
  destination_file: str
  apply: bool = False
Returns: RefactorResult
```
- Engine: rope `Move`

### Search Tools (tools/search.py)

#### `find_constructors`
```
Parameters:
  class_name: str
  file_path: str | None = None  # File containing the class (optional, for disambiguation)
Returns: list[ConstructorSite]
```
- Strategy: Pyright `find_references` on the class name → filter to call sites (not imports, not type annotations)
- Parse arguments at each call site

#### `structural_search`
```
Parameters:
  pattern: str            # ast-grep or LibCST pattern string
  file_path: str | None = None  # None = search whole project
  language: str = "python"
Returns: list[StructuralMatch]
```
- Engine: LibCST `matchers` module for pattern matching
- Pattern syntax: LibCST matcher DSL (e.g., `m.Call(func=m.Name("MyClass"))`)

#### `dead_code_detection`
```
Parameters:
  file_path: str | None = None  # None = whole project
Returns: list[DeadCodeItem]
```
- Strategy: Pyright diagnostics for unused imports + Pyright `find_references` returning 0 results for module-level names
- Checks: functions, classes, module-level variables with no references outside their own file

#### `suggest_imports`
```
Parameters:
  symbol: str             # Unresolved symbol name
  file_path: str          # File context
Returns: list[ImportSuggestion]
```
- Primary: Pyright code actions (`textDocument/codeAction` with diagnostic context)
- Fallback: Jedi `Script.get_names(all_scopes=True)` search

### Composite Tools (tools/composite.py)

#### `smart_rename`
```
Parameters:
  file_path: str
  line: int
  character: int
  new_name: str
  apply: bool = False
Returns: RefactorResult
```
- Orchestration:
  1. Pyright `find_references` to identify all sites
  2. rope `Rename` to generate edits
  3. If `apply=True`: write edits, then re-run Pyright diagnostics on affected files
  4. Return edits + post-rename diagnostics

---

## Backend Specifications

### Pyright LSP Bridge (backends/pyright_lsp.py)

This is the most complex backend. It manages a Pyright language server subprocess.

**Lifecycle:**
1. On server startup (lifespan), spawn `pyright-langserver --stdio` as a subprocess
2. Send LSP `initialize` request with workspace root and client capabilities
3. Send `initialized` notification
4. Open files via `textDocument/didOpen` on demand (lazy — only when a tool references a file)
5. Track open files to avoid duplicate `didOpen`
6. On server shutdown, send `shutdown` + `exit`

**Key implementation details:**
- Use `asyncio.subprocess` for non-blocking I/O with the Pyright process
- LSP messages are JSON-RPC over stdio with `Content-Length` headers
- Maintain a pending requests dict (`dict[int, asyncio.Future]`) keyed by request ID
- A background reader task reads from Pyright's stdout, parses messages, and resolves futures or handles notifications
- Diagnostics come as `textDocument/publishDiagnostics` notifications — store latest per file in a `dict[str, list[Diagnostic]]`
- All LSP requests must be serialized via an `asyncio.Lock` (Pyright processes requests sequentially)

**Required LSP methods to implement:**
- `textDocument/hover`
- `textDocument/definition`
- `textDocument/references`
- `textDocument/prepareCallHierarchy`
- `callHierarchy/incomingCalls`
- `callHierarchy/outgoingCalls`
- `textDocument/codeAction`
- `textDocument/publishDiagnostics` (notification handler)
- `textDocument/didOpen`
- `textDocument/didChange`
- `textDocument/didClose`

**File path handling:**
- Convert OS paths to `file:///` URIs for LSP
- Convert LSP URIs back to OS paths for tool responses
- Handle Windows drive letter casing (`C:` vs `c:`)

### Jedi Backend (backends/jedi_backend.py)

**Lifecycle:**
1. On startup, detect Python environment (venv path, Python version) from workspace
2. Create a `jedi.Project` with detected environment
3. Per-request: create `jedi.Script(source, path=file_path, project=project)`

**Methods:**
- `get_references(file_path, line, character)` → `list[Location]`
- `goto_definition(file_path, line, character)` → `list[Location]`
- `infer_type(file_path, line, character)` → `TypeInfo | None`
- `get_completions(file_path, line, character)` → used internally by `suggest_imports`
- `search_names(symbol, all_scopes=True)` → for import suggestions

**Threading:** Jedi is not async-safe. All Jedi calls MUST go through `asyncio.to_thread()`.

**Line numbering:** Jedi uses 1-based lines, 0-based columns. Convert to/from the 0-based Position model.

### rope Backend (backends/rope_backend.py)

**Lifecycle:**
1. On startup, create `rope.base.project.Project(workspace_root)`
2. Before each refactoring, call `project.validate()` to sync file state

**Methods (all return list[TextEdit]):**
- `rename(file_path, offset, new_name)` → TextEdit list
- `extract_method(file_path, start_offset, end_offset, method_name)` → TextEdit list
- `extract_variable(file_path, start_offset, end_offset, variable_name)` → TextEdit list
- `inline(file_path, offset)` → TextEdit list
- `move(source_file, symbol_name, destination_file)` → TextEdit list

**Offset conversion:** rope uses byte offsets from file start. Implement `position_to_offset(file_path, line, character) -> int` and `offset_to_position(file_path, offset) -> Position` converters.

**Threading:** rope is not async-safe. All rope calls MUST go through `asyncio.to_thread()`.

**Change application:** When `apply=True`:
1. rope's `changes.get_changed_contents()` returns `dict[str, str]` (file_path → new_content)
2. Write atomically (write to `.tmp`, rename)
3. Send `textDocument/didChange` to Pyright for each modified file
4. Collect fresh diagnostics

---

## Server Configuration (config.py)

Auto-discover from workspace root:

```python
@dataclass(slots=True)
class ServerConfig:
    workspace_root: Path
    python_executable: Path          # From venv or system
    venv_path: Path | None
    pyright_executable: str          # "pyright-langserver" (from pip) or custom path
    pyrightconfig_path: Path | None  # Detected pyrightconfig.json
    rope_prefs: dict[str, object]    # rope preferences (from .ropeproject or defaults)
```

Discovery order for Python environment:
1. `.venv/` or `venv/` directory in workspace root
2. `pyproject.toml` `[tool.poetry.virtualenvs]` path
3. `VIRTUAL_ENV` environment variable
4. System `python3` / `python`

The workspace root is passed via the MCP initialization. Use `ctx.request_context` or server lifespan to receive it. In stdio mode, accept it as a CLI argument: `python -m python_refactor_mcp /path/to/project`.

---

## Server Entry Point (server.py)

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP, Context

@dataclass
class AppContext:
    pyright: PyrightLSPClient
    jedi: JediBackend
    rope: RopeBackend
    config: ServerConfig

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    config = discover_config(workspace_root)
    pyright = PyrightLSPClient(config)
    jedi_be = JediBackend(config)
    rope_be = RopeBackend(config)
    
    await pyright.start()
    jedi_be.initialize()
    rope_be.initialize()
    
    try:
        yield AppContext(pyright=pyright, jedi=jedi_be, rope=rope_be, config=config)
    finally:
        await pyright.shutdown()
        rope_be.close()

mcp = FastMCP(
    "Python Refactor",
    lifespan=app_lifespan,
)

# Register all tools from tools/ modules
# Each tool accesses backends via ctx.request_context.lifespan_context
```

---

## Quality Gates

Run these after every stage:

```powershell
# Lint
python -m ruff check .

# Type check (strict)
python -m pyright .
python -m mypy .

# Tests
python -m pytest tests/unit/ -v
python -m pytest tests/integration/ -v  # (from Stage 5+)
```

---

# IMPLEMENTATION STAGES

Each stage is designed to be completed in one agent session. Each stage builds on the previous stage's output. Do NOT skip ahead or implement features from later stages.

---

## Stage 1: Project Scaffold + MCP Server Shell + Models

### Goal
Create the complete project structure, all config files, shared models, and a working MCP server that starts, connects via stdio, and responds to `list_tools` with placeholder tools.

### Deliverables

1. **pyproject.toml** with:
   - `[project]`: name=`python-refactor-mcp`, version=`0.1.0`, requires-python=`>=3.13`
   - Dependencies: `mcp>=1.20`, `pydantic>=2.0`, `jedi>=0.19`, `rope>=1.13`, `pyright>=1.1.380`
   - Dev dependencies: `pytest>=8.0`, `pytest-asyncio>=0.24`, `ruff>=0.8`, `mypy>=1.13`
   - `[project.scripts]`: `python-refactor-mcp = "python_refactor_mcp.__main__:main"`

2. **pyrightconfig.json**: strict mode, include `src/`, exclude `tests/`

3. **.gitignore**: standard Python + `.ropeproject/` + `dist/` + `build/`

4. **src/python_refactor_mcp/__init__.py**: `__version__ = "0.1.0"`

5. **src/python_refactor_mcp/__main__.py**: Parse CLI args (`sys.argv[1]` = workspace root), call `server.run_server(workspace_root)`

6. **src/python_refactor_mcp/models.py**: All Pydantic models listed in the Shared Models section above. Every model, every field.

7. **src/python_refactor_mcp/config.py**: `ServerConfig` dataclass + `discover_config(workspace_root: Path) -> ServerConfig` with full auto-discovery logic (venv detection, pyright executable detection, pyrightconfig.json detection).

8. **src/python_refactor_mcp/server.py**: FastMCP instance with lifespan that creates `AppContext` with stubbed backends. Register 15 placeholder tools (all tools from the Tool Surface section) that return `"Not yet implemented"` with correct parameter signatures and docstrings. The tools must have the correct type-annotated parameters matching the Tool Surface spec. Use `ctx.request_context.lifespan_context` to access `AppContext`.

9. **All `__init__.py` files** for every package/subpackage.

10. **tests/conftest.py** with basic fixtures (tmp workspace path, sample Python files).

11. **README.md** with project overview, installation instructions, and MCP client configuration example.

12. **AGENTS.md** pointing to build/test commands.

### Verification
- `python -m ruff check .` passes
- `python -m pyright .` passes (strict mode)
- `python -m python_refactor_mcp /some/path` starts and responds to MCP `initialize` + `list_tools` (returns 15 tools)
- `python -m pytest tests/unit/ -v` passes (test that models can be constructed)

---

## Stage 2: Pyright LSP Bridge

### Goal
Implement the full Pyright language server subprocess management and LSP client. This is the most complex single component.

### Deliverables

1. **src/python_refactor_mcp/util/lsp_types.py**: LSP protocol type definitions as TypedDicts or dataclasses:
   - `InitializeParams`, `InitializeResult`
   - `TextDocumentIdentifier`, `TextDocumentItem`, `TextDocumentPositionParams`
   - `DidOpenTextDocumentParams`, `DidChangeTextDocumentParams`, `DidCloseTextDocumentParams`
   - `ReferenceParams`, `HoverParams`, `DefinitionParams`
   - `CallHierarchyPrepareParams`, `CallHierarchyIncomingCallsParams`, `CallHierarchyOutgoingCallsParams`
   - `CodeActionParams`
   - `PublishDiagnosticsParams`
   - Response types for each request

2. **src/python_refactor_mcp/util/lsp_client.py**: Generic async LSP client:
   - `class LSPClient`: manages `asyncio.subprocess.Process`
   - `async start(command: list[str])`: spawn subprocess
   - `async send_request(method: str, params: dict) -> dict`: send JSON-RPC request, return response
   - `async send_notification(method: str, params: dict)`: send without expecting response
   - Background reader coroutine that:
     - Reads `Content-Length` headers from stdout
     - Parses JSON-RPC messages
     - Routes responses to pending `asyncio.Future`s by ID
     - Routes notifications to registered handlers
   - `async shutdown()`: send `shutdown` request + `exit` notification + terminate process
   - Request ID counter (atomic int)
   - Pending requests: `dict[int, asyncio.Future[dict]]`
   - Notification handlers: `dict[str, Callable]`

3. **src/python_refactor_mcp/backends/pyright_lsp.py**: Pyright-specific LSP client:
   - `class PyrightLSPClient`:
     - Wraps `LSPClient` with Pyright-specific initialization
     - `async start()`: spawn `pyright-langserver --stdio`, send `initialize` with capabilities, send `initialized`
     - `_open_files: set[str]` tracking
     - `_diagnostics: dict[str, list[Diagnostic]]` from notifications
     - `async ensure_file_open(file_path: str)`: read file, send `didOpen` if not tracked
     - `async notify_file_changed(file_path: str)`: send `didChange` with full content
     - `async get_hover(file_path, line, char) -> TypeInfo | None`
     - `async get_references(file_path, line, char, include_declaration) -> list[Location]`
     - `async get_definition(file_path, line, char) -> list[Location]`
     - `async prepare_call_hierarchy(file_path, line, char) -> list[CallHierarchyItem]`
     - `async get_incoming_calls(item) -> list[CallHierarchyItem]`
     - `async get_outgoing_calls(item) -> list[CallHierarchyItem]`
     - `async get_code_actions(file_path, range, diagnostics) -> list[dict]`
     - `async get_diagnostics(file_path: str | None) -> list[Diagnostic]`
     - `async shutdown()`
   - Path URI conversion utilities: `path_to_uri(path: str) -> str`, `uri_to_path(uri: str) -> str`

4. **tests/unit/test_pyright_lsp.py**:
   - Test LSP message framing (Content-Length encoding/decoding)
   - Test request/response ID correlation
   - Test notification routing
   - Test path/URI conversion (Windows paths with drive letters)
   - Mock subprocess for unit tests — do NOT require actual Pyright installation
   - Test file tracking (ensure_file_open dedup)

### Verification
- All quality gates pass (ruff, pyright strict, mypy)
- Unit tests pass with mocked subprocess
- (Manual) If `pyright` pip package is installed, server can start and return hover info for a simple file

---

## Stage 3: Jedi + rope Backends

### Goal
Implement the Jedi analysis fallback backend and the rope refactoring backend.

### Deliverables

1. **src/python_refactor_mcp/backends/jedi_backend.py**:
   - `class JediBackend`:
     - `__init__(config: ServerConfig)`
     - `initialize()`: create `jedi.Project`
     - `_make_script(file_path: str, source: str | None = None) -> jedi.Script`: create Script with project context. If source is None, read from disk.
     - `async get_references(file_path, line, character) -> list[Location]`: wraps `Script.get_references()` via `asyncio.to_thread()`. Jedi uses 1-based lines — convert.
     - `async goto_definition(file_path, line, character) -> list[Location]`
     - `async infer_type(file_path, line, character) -> TypeInfo | None`
     - `async search_names(symbol: str) -> list[ImportSuggestion]`

2. **src/python_refactor_mcp/backends/rope_backend.py**:
   - `class RopeBackend`:
     - `__init__(config: ServerConfig)`
     - `initialize()`: create `rope.base.project.Project`
     - `close()`: close rope project
     - Helper: `_position_to_offset(file_path: str, line: int, character: int) -> int`
     - Helper: `_offset_to_position(file_path: str, offset: int) -> Position`
     - Helper: `_changes_to_edits(changes: rope.base.change.ChangeSet) -> list[TextEdit]`
     - Helper: `_apply_changes(changes: rope.base.change.ChangeSet) -> list[str]` (returns affected file paths)
     - `async rename(file_path, line, character, new_name, apply) -> RefactorResult`: via `asyncio.to_thread()`
     - `async extract_method(file_path, start_line, start_char, end_line, end_char, method_name, apply) -> RefactorResult`
     - `async extract_variable(file_path, start_line, start_char, end_line, end_char, variable_name, apply) -> RefactorResult`
     - `async inline(file_path, line, character, apply) -> RefactorResult`
     - `async move(source_file, symbol_name, destination_file, apply) -> RefactorResult`

3. **src/python_refactor_mcp/util/diff.py**:
   - `apply_text_edits(file_path: str, edits: list[TextEdit]) -> str`: apply edits to file content, return new content
   - `write_atomic(file_path: str, content: str) -> None`: write via tmp+rename

4. **tests/unit/test_jedi_backend.py**:
   - Test with real Jedi (it's fast enough for unit tests) against small fixture files
   - Test line number conversion (1-based Jedi → 0-based model)
   - Test reference finding, definition goto, type inference

5. **tests/unit/test_rope_backend.py**:
   - Test with real rope against fixture files in tmp_path
   - Test rename generates correct TextEdits
   - Test extract_method on a simple function
   - Test offset conversion round-trips
   - Test apply=True writes files

### Verification
- All quality gates pass
- Unit tests use real Jedi and rope (no mocking needed — they're pure Python)
- Backend methods return correctly structured model objects

---

## Stage 4: Tool Implementations (Analysis + Navigation + Refactoring)

### Goal
Replace all placeholder tool implementations with real logic that orchestrates the backends. Implement the fallback patterns (Pyright primary → Jedi fallback).

### Deliverables

1. **src/python_refactor_mcp/tools/analysis.py** — Full implementations of:
   - `find_references`: Pyright primary, Jedi fallback if 0 results, merge/dedup
   - `get_type_info`: Pyright hover primary, Jedi infer fallback
   - `get_diagnostics`: Pyright diagnostics store

2. **src/python_refactor_mcp/tools/navigation.py** — Full implementations of:
   - `call_hierarchy`: Pyright call hierarchy with depth traversal
   - `goto_definition`: Pyright primary, Jedi fallback

3. **src/python_refactor_mcp/tools/refactoring.py** — Full implementations of:
   - `rename_symbol`: rope rename
   - `extract_method`: rope extract
   - `extract_variable`: rope extract
   - `inline_variable`: rope inline
   - `move_symbol`: rope move
   - All include post-refactor Pyright diagnostic validation when `apply=True`

4. **src/python_refactor_mcp/server.py** — Update tool registrations to call real implementations. Each `@mcp.tool()` handler accesses `AppContext` via `ctx.request_context.lifespan_context` and delegates to the appropriate tool function.

5. **tests/unit/test_analysis_tools.py**: Mock the backends, verify fallback logic
6. **tests/unit/test_navigation_tools.py**: Mock backends, verify delegation
7. **tests/unit/test_refactoring_tools.py**: Mock rope backend, verify apply/no-apply paths

### Verification
- All quality gates pass
- Unit tests verify fallback: when Pyright returns empty, Jedi is called
- Unit tests verify refactor: rope edits are correctly structured
- Unit tests verify apply path: file writes + diagnostic recheck

---

## Stage 5: Search + Composite Tools + Integration Tests

### Goal
Implement the remaining search and composite tools. Build the integration test fixture project and end-to-end tests.

### Deliverables

1. **src/python_refactor_mcp/tools/search.py** — Full implementations of:
   - `find_constructors`: Pyright references → filter to Call nodes
   - `structural_search`: LibCST matchers (add `libcst>=1.1` to dependencies)
   - `dead_code_detection`: Pyright diagnostics + reference count = 0
   - `suggest_imports`: Pyright code actions + Jedi name search

2. **src/python_refactor_mcp/tools/composite.py** — Full implementations of:
   - `smart_rename`: Pyright refs → rope rename → Pyright validate

3. **tests/integration/fixtures/sample_project/**: A complete small Python project:
   - `src/models.py`: 2-3 dataclasses with constructors
   - `src/service.py`: Functions that construct and use the models
   - `src/utils.py`: Utility functions (candidates for extract/inline testing)
   - `tests/test_models.py`: Simple tests importing from models
   - `pyproject.toml` with minimal config

4. **tests/integration/conftest.py**: Fixtures that:
   - Copy the fixture project to a temp directory
   - Start the MCP server as a subprocess
   - Connect to it via MCP client SDK (`stdio_client`)
   - Provide a `session` fixture for calling tools

5. **tests/integration/test_end_to_end.py**:
   - Test `find_references` returns correct locations for a class
   - Test `get_type_info` returns type for a variable
   - Test `get_diagnostics` finds errors in a file with intentional type errors
   - Test `rename_symbol` with `apply=False` returns correct edits
   - Test `rename_symbol` with `apply=True` modifies files on disk
   - Test `find_constructors` finds all `MyClass(...)` call sites
   - Test `smart_rename` end-to-end with validation

6. **tests/unit/test_search_tools.py**: Unit tests for search tools
7. **tests/unit/test_composite_tools.py**: Unit tests for composite orchestration

### Verification
- All quality gates pass
- `python -m pytest tests/unit/ -v` — all pass
- `python -m pytest tests/integration/ -v` — all pass (requires `pyright` pip package installed)

---

## Stage 6: Build, Packaging, and Final Polish

### Goal
PyInstaller packaging, final documentation, CI configuration, and end-to-end verification.

### Deliverables

1. **scripts/build.ps1**: PyInstaller build script:
   - Builds `python-refactor-mcp.exe` from `__main__.py`
   - NOTE: The exe bundles the Python server only. Pyright (`pyright-langserver`) must be available on PATH or installed via pip in the user's environment. Document this requirement.

2. **pyproject.toml updates**: Add PyInstaller to optional build dependencies

3. **README.md updates**: Complete documentation:
   - Installation via pip and via exe
   - MCP client configuration for VS Code Copilot / Claude Desktop
   - Configuration: how auto-discovery works, how to override
   - Tool reference table with all 15 tools
   - Troubleshooting section (Pyright not found, venv not detected, etc.)
   - Architecture diagram (text)

4. **AGENTS.md**: Agent guidelines with quality gate commands

5. **.github/copilot-instructions.md**: Repository instructions for AI agents

6. **Final quality sweep**:
   - All ruff rules pass
   - pyright strict passes
   - mypy passes
   - All unit + integration tests pass
   - Manual test: configure in VS Code as MCP server, call `find_references` and `rename_symbol` on a real project

### Verification
- `scripts/build.ps1` produces a working exe
- `python -m pytest tests/ -v` — all tests pass
- Manual: MCP Inspector connects and all 15 tools are listed with correct schemas
- Manual: At least `find_references`, `get_type_info`, and `rename_symbol` work against a real Python project

---

## Cross-Stage Rules

1. **Never use `Any` type** — always use specific types or `object` when truly unknown.
2. **Every public function has a docstring** — one-liner minimum.
3. **Every backend call through `asyncio.to_thread()`** — Jedi and rope are synchronous; never call them directly from an async context.
4. **Every file path in tool responses is absolute** — OS-native path separators.
5. **Error handling:** Backend failures (Pyright subprocess crash, rope refactoring error, Jedi parse error) should return structured error responses, not raise unhandled exceptions. Use `try/except` at the tool level and return `CallToolResult` with `isError=True` content.
6. **Logging:** Use `await ctx.info()` / `await ctx.debug()` for MCP-visible logging. Use Python `logging` module for internal debug logging.
7. **Tests:** Every stage must leave all existing tests passing. Never break a prior stage's tests.
