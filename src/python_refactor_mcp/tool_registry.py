"""Declarative tool-registration table for the MCP server.

This module holds the *pure-delegation* tool functions — those whose body is the
canonical five-line shape ``app = get_current_backends()`` / ``result = await
<module>.<fn>(app.<backend>, ...)`` / ``_LOGGER.debug(...)`` / ``return
result``.  Each function is registered on the MCPServer instance by
:func:`register_tools`, which applies ``tool_error_boundary`` and then
``mcp.add_tool(...)`` for every :class:`ToolRecord`.

Why the delegates stay as real ``async def`` functions (rather than a ``(name,
callable, debug_fmt_fn)`` data tuple): MCPServer derives each tool's *name*,
input schema, and structured-output model from the wrapped function's
``__name__``, signature, and return annotation via ``inspect.signature(...,
eval_str=True)`` and ``typing.get_type_hints(...)``.  Both follow
``functools.wraps``'s ``__wrapped__`` chain, so ``tool_error_boundary`` (which
uses ``@wraps``) transparently exposes each delegate's true signature.  A
factory that synthesised ``(*args, **kwargs)`` wrappers would erase that
signature and corrupt every schema, and the per-tool argument threading
(``app.pyright`` vs ``app.jedi`` vs ``app.rope``, bespoke arg order) is not
uniform enough to drive from data alone. The standard-library debug log the plan
modelled as ``debug_fmt_fn`` is therefore kept inline in each delegate.

The eleven wrappers with non-trivial bodies (conditionals, multi-branch backend
selection, or aliased imports) remain explicit :class:`ToolRecord` entries in
``server.py::EXPLICIT_TOOL_RECORDS``. The server passes them to
:func:`register_tools` through ``extra_records`` so both wrapper families share
one registration and error-boundary path.

``eval_str=True`` means every annotation referenced by a delegate must resolve
in this module's namespace; that is why the model types below are imported here
even though they look unused to a casual reader — they are load-bearing for
runtime schema generation.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from python_refactor_mcp.config import TOOL_PROFILES, ToolProfile
from python_refactor_mcp.models import (
    CallHierarchyResult,
    CodeMetricsResult,
    ConstructorSearchResult,
    CouplingMetricsResult,
    DependencyGraph,
    Diagnostic,
    DiffPreview,
    DocumentationResult,
    DocumentHighlight,
    DuplicateCodeResult,
    EnvironmentInfo,
    FoldingRange,
    HistoryEntry,
    ImportSuggestion,
    InferredType,
    InterfaceComparison,
    LayerViolationResult,
    Location,
    NameEntry,
    PaginatedDeadCode,
    PaginatedDiagnosticSummary,
    Position,
    PrepareRenameResult,
    ProtocolSource,
    PublicAPIItem,
    RefactorResult,
    ReferenceResult,
    ScopeContext,
    SelectionRangeResult,
    SemanticToken,
    SignatureInfo,
    SignatureOperation,
    StaticError,
    StructuralSearchResult,
    SymbolAnchor,
    SymbolInfo,
    SymbolSearchResult,
    SyntaxErrorItem,
    TestImpactResult,
    TextEdit,
    TransactionResult,
    TypeCoverageReport,
    TypeHierarchyResult,
    TypeHintResult,
    TypeInfo,
    TypeStubFreshnessResult,
    TypeUsersResult,
)
from python_refactor_mcp.tool_runtime import get_current_backends, tool_error_boundary
from python_refactor_mcp.tools import analysis, composite, metrics, navigation, refactoring, search

_LOGGER = logging.getLogger(__name__)

# Tool annotation constants. Defined here (the registration owner) and imported
# by ``server.py`` for its explicit wrappers. Values pass through per tool and
# are never collapsed to a single default.
READ_ONLY_ANNOTATIONS = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
DESTRUCTIVE_ANNOTATIONS = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
)
ADDITIVE_ANNOTATIONS = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)


# ═══════════════════════════════════════════════════════════════════════════
#  Pure-delegation tool functions
#
#  Each function below is a plain ``async def`` (no decorator).  It carries its
#  real signature, docstring, and return annotation so MCPServer can introspect
#  it.  Registration (``_tool_error_boundary`` + ``mcp.add_tool``) happens in
#  :func:`register_tools` via the :data:`TOOL_RECORDS` table at the bottom.
# ═══════════════════════════════════════════════════════════════════════════


async def find_references(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    include_declaration: bool = True,
    include_context: bool = False,
    limit: int | None = None,
) -> ReferenceResult:
    """Find all references to a symbol across the workspace. Use when you need to understand how widely a function, class, or variable is used before renaming, moving, or deleting it. Returns merged Pyright/Jedi locations and typed `backend_failures` when optional enrichment is incomplete. Set include_context=True to get surrounding source lines. Related: prepare_rename, rename_symbol. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await analysis.find_references(
        app.pyright,
        app.jedi,
        file_path,
        line,
        character,
        include_declaration,
        include_context,
        limit,
    )
    _LOGGER.debug("find_references source=%s count=%s", result.source, result.total_count)
    return result


async def find_type_users(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    kinds: list[str] | None = None,
    include_declaration: bool = False,
    limit: int | None = None,
) -> TypeUsersResult:
    """Inverse of `find_references` scoped to a type — classify every reference site as `annotation` (type-hint position incl. subscripts like `list[Foo]`), `instantiation` (head of a `Foo(...)` call), `subclass` (in a `ClassDef.bases` list), or `other` (e.g. `isinstance(x, Foo)`, `Foo.classmethod`). Returns per-site classification plus aggregate `by_kind` counts. Pass `kinds=['annotation']` to filter; defaults to all four buckets. `include_declaration` defaults to False (the class definition itself is rarely an interesting type *use*). Related: find_references, type_hierarchy, find_implementations. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await analysis.find_type_users(
        app.pyright,
        app.jedi,
        file_path,
        line,
        character,
        kinds,
        include_declaration,
        limit,
    )
    _LOGGER.debug(
        "find_type_users by_kind=%s total=%s truncated=%s", result.by_kind, result.total_count, result.truncated
    )
    return result


async def get_type_info(ctx: Context, file_path: str, line: int, character: int) -> TypeInfo:
    """Infer the type of a symbol or expression at a source position. Use when you need to understand what type a variable holds, what a function returns, or what class an object is. Tries Pyright first with Jedi fallback for dynamic code. Related: get_documentation, get_type_hint_string. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await analysis.get_type_info(app.pyright, app.jedi, file_path, line, character)
    _LOGGER.debug("get_type_info source=%s type=%s", result.source, result.type_string)
    return result


async def get_documentation(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    source: str | None = None,
) -> DocumentationResult:
    """Get detailed documentation and docstrings for a symbol. Use when you need full API docs, function signatures, or module-level help. Powered by Jedi for rich dynamic analysis. Pass source to analyze in-memory content. Related: get_type_info (for type only), get_signature_help (for call-site params). Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await analysis.get_documentation(app.jedi, file_path, line, character, source)
    _LOGGER.debug("get_documentation entries=%s", len(result.entries))
    return result


async def get_signature_help(ctx: Context, file_path: str, line: int, character: int) -> SignatureInfo | None:
    """Get function signature help at a call site. Use when the cursor is inside a function call's parentheses to see parameter names, types, and which parameter is active. Tries Pyright first, falls back to Jedi for dynamic code. Related: get_completions, get_documentation. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await analysis.get_signature_help(app.pyright, file_path, line, character, jedi=app.jedi)
    _LOGGER.debug("get_signature_help found=%s", result is not None)
    return result


async def get_document_highlights(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
) -> list[DocumentHighlight]:
    """Highlight all read and write accesses of a symbol within a single file. Use to understand how a variable is used locally — which lines read it vs. which lines assign to it. Related: find_references (cross-file). Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await analysis.get_document_highlights(app.pyright, file_path, line, character)
    _LOGGER.debug("get_document_highlights count=%s", len(result))
    return result


async def get_semantic_tokens(ctx: Context, file_path: str, limit: int | None = None) -> list[SemanticToken]:
    """Get semantic token classifications for a file. Returns token type and modifier info for every symbol. Use for syntax-aware highlighting or to understand which tokens are namespaces, types, functions, etc. Can return large payloads — use limit to cap results. Related: get_inlay_hints."""
    app = get_current_backends()
    result = await analysis.get_semantic_tokens(app.pyright, file_path, limit)
    _LOGGER.debug("get_semantic_tokens count=%s", len(result))
    return result


async def get_diagnostics(
    ctx: Context,
    file_path: str | None = None,
    severity_filter: str | None = None,
    limit: int | None = None,
    suppress_codes: list[str] | None = None,
    file_paths: list[str] | None = None,
) -> list[Diagnostic]:
    """Get type-checking diagnostics (errors, warnings, hints) for one file, a batch of files, or the full project. Use after refactoring to verify no errors were introduced, or to audit code quality. Filter by severity_filter and suppress_codes to reduce noise. Related: get_workspace_diagnostics (aggregated counts)."""
    app = get_current_backends()
    result = await analysis.get_diagnostics(
        app.pyright,
        file_path,
        severity_filter,
        limit,
        suppress_codes,
        file_paths,
    )
    _LOGGER.debug("get_diagnostics count=%s severity_filter=%s", len(result), severity_filter)
    return result


async def get_workspace_diagnostics(
    ctx: Context,
    root_path: str | None = None,
    suppress_codes: list[str] | None = None,
    file_paths: list[str] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> PaginatedDiagnosticSummary:
    """Get aggregated diagnostic counts (errors, warnings, hints) per file across the workspace. Use for a high-level health overview of the codebase. Supports pagination via offset/limit. Related: get_diagnostics (detailed per-file diagnostics)."""
    app = get_current_backends()
    result = await analysis.get_workspace_diagnostics(
        app.pyright,
        app.config,
        root_path,
        suppress_codes,
        file_paths,
        offset,
        limit,
    )
    _LOGGER.debug("get_workspace_diagnostics files=%s total=%s", len(result.items), result.total_count)
    return result


async def deep_type_inference(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
) -> list[InferredType]:
    """Follow imports and statements to resolve final types at a position. Goes deeper than get_type_info by tracing through assignments and imports to their ultimate definitions. Use when get_type_info returns 'Unknown' for dynamic code. Related: get_type_info, get_type_hint_string. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await analysis.deep_type_inference(app.jedi, file_path, line, character)
    _LOGGER.debug("deep_type_inference count=%s", len(result))
    return result


async def get_type_hint_string(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
) -> list[TypeHintResult]:
    """Return ready-to-use type annotation strings like ``Iterable[int]`` for a symbol. Use when adding missing type hints — provides copy-paste-ready annotations. Related: deep_type_inference, get_type_info. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await analysis.get_type_hint_string(app.jedi, file_path, line, character)
    _LOGGER.debug("get_type_hint_string count=%s", len(result))
    return result


async def get_syntax_errors(ctx: Context, file_path: str) -> list[SyntaxErrorItem]:
    """Detect syntax errors via Jedi's parser. Complements Pyright diagnostics with an independent syntax check. Use to quickly find parse errors before running full type analysis. Related: get_diagnostics."""
    app = get_current_backends()
    result = await analysis.get_syntax_errors(app.jedi, file_path)
    _LOGGER.debug("get_syntax_errors count=%s", len(result))
    return result


async def get_context(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
) -> ScopeContext | None:
    """Return the enclosing function, class, or module scope at a position. Use to understand code structure and what scope a given line belongs to. Related: get_symbol_outline, call_hierarchy. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await analysis.get_context(app.jedi, file_path, line, character)
    _LOGGER.debug("get_context kind=%s", result.kind if result else "none")
    return result


async def get_all_names(
    ctx: Context,
    file_path: str,
    all_scopes: bool = True,
    references: bool = False,
) -> list[NameEntry]:
    """List all defined names in a file with optional nested scopes. Broader than get_symbol_outline — includes references and nested scopes when enabled. Use to audit all names used in a file. Related: get_symbol_outline, search_symbols."""
    app = get_current_backends()
    result = await analysis.get_all_names(app.jedi, file_path, all_scopes, references)
    _LOGGER.debug("get_all_names count=%s", len(result))
    return result


async def create_type_stubs(ctx: Context, package_name: str, output_dir: str | None = None) -> bool:
    """Generate .pyi type stub files for a third-party package lacking type information. Use to improve type checking for untyped dependencies. The package_name is the import name (e.g., 'requests'). Optional output_dir specifies where to write stubs. Related: get_diagnostics, get_type_info."""
    app = get_current_backends()
    result = await analysis.create_type_stubs(app.pyright, package_name, output_dir)
    _LOGGER.debug("create_type_stubs package=%s success=%s", package_name, result)
    return result


async def check_type_stub_freshness(
    ctx: Context,
    source_file: str,
    stub_file: str | None = None,
) -> TypeStubFreshnessResult:
    """Compare a Python module's public callable signatures with its `.pyi` stub. Defaults stub_file to the adjacent same-name `.pyi`. Reports missing callables and calling-convention drift while conservatively skipping overload sets and Protocol classes. Related: create_type_stubs, get_type_coverage."""
    result = analysis.check_type_stub_freshness(source_file, stub_file)
    _LOGGER.debug(
        "check_type_stub_freshness fresh=%s missing_stub=%s missing_source=%s mismatches=%s",
        result.fresh,
        len(result.missing_in_stub),
        len(result.missing_in_source),
        len(result.signature_mismatches),
    )
    return result


async def call_hierarchy(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    direction: str = "both",
    depth: int = 1,
    max_items: int | None = 200,
) -> CallHierarchyResult:
    """Discover which functions call a given function (callers) and which functions it calls (callees). Use to understand call chains before refactoring. Set direction to 'callers', 'callees', or 'both'. Increase depth for deeper traversal. Related: type_hierarchy, find_references. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await navigation.call_hierarchy(app.pyright, file_path, line, character, direction, depth, max_items)
    _LOGGER.debug(
        "call_hierarchy callers=%s callees=%s depth=%s direction=%s",
        len(result.callers),
        len(result.callees),
        depth,
        direction,
    )
    return result


async def test_impact_select(
    ctx: Context,
    symbols: list[SymbolAnchor],
    depth: int = 2,
    max_items: int = 200,
) -> TestImpactResult:
    """Given changed symbol anchors, return the pytest tests that transitively exercise them. Each anchor has file_path, line, and character. Traverses the call-hierarchy callers graph per anchor and keeps callers in test files, emitting best-effort `<file_path>::<symbol>` pytest node IDs (parametrized/nested-class tests are not resolved to exact collected IDs). Related: call_hierarchy, get_test_coverage_map. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await analysis.test_impact_select(app.pyright, symbols, depth, max_items)
    _LOGGER.debug("test_impact_select entries=%s tests=%s", len(result.entries), result.total_affected_tests)
    return result


async def goto_definition(ctx: Context, file_path: str, line: int, character: int) -> list[Location]:
    """Jump to where a symbol is defined. Use when you encounter a function call, variable, or import and want to see its implementation. Follows imports to their source. Combines Pyright and Jedi for best coverage. Related: get_declaration, get_type_definition, find_implementations. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await navigation.goto_definition(app.pyright, app.jedi, file_path, line, character)
    _LOGGER.debug("goto_definition count=%s", len(result))
    return result


async def type_hierarchy(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    direction: str = "both",
    depth: int = 3,
    max_items: int | None = 200,
    class_name: str | None = None,
) -> TypeHierarchyResult:
    """Discover class inheritance — supertypes (parents) and subtypes (children) of a class. Use to understand class hierarchies before refactoring or to find all implementations of a base class. Set direction to 'supertypes', 'subtypes', or 'both'. Related: call_hierarchy, find_implementations. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await navigation.type_hierarchy(
        app.pyright,
        file_path,
        line,
        character,
        direction,
        depth,
        max_items,
        class_name,
    )
    _LOGGER.debug(
        "type_hierarchy supertypes=%s subtypes=%s depth=%s direction=%s",
        len(result.supertypes),
        len(result.subtypes),
        depth,
        direction,
    )
    return result


async def selection_range(ctx: Context, file_path: str, positions: list[Position]) -> list[SelectionRangeResult]:
    """Get nested selection ranges (inner-most to outer-most scope) at source positions. Use for smart expand/shrink selection — progressively selects expression, statement, block, function, class, module. Related: get_folding_ranges. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await navigation.selection_range(app.pyright, file_path, positions)
    _LOGGER.debug("selection_range count=%s", len(result))
    return result


async def find_implementations(ctx: Context, file_path: str, line: int, character: int) -> list[Location]:
    """Find concrete implementations of an abstract method or protocol. Use when you have a base class method and need to find all classes that implement it. Related: type_hierarchy, goto_definition. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await navigation.find_implementations(app.pyright, file_path, line, character)
    _LOGGER.debug("find_implementations count=%s", len(result))
    return result


async def get_declaration(ctx: Context, file_path: str, line: int, character: int) -> list[Location]:
    """Navigate to the declaration site of a symbol (where it is first declared, not necessarily defined). For most Python code, this is equivalent to goto_definition. Related: goto_definition, get_type_definition. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await navigation.get_declaration(app.pyright, file_path, line, character)
    _LOGGER.debug("get_declaration count=%s", len(result))
    return result


async def get_type_definition(ctx: Context, file_path: str, line: int, character: int) -> list[Location]:
    """Navigate to the type definition of a symbol (e.g., from a variable to its class definition). Use when you want to see the class behind an instance, not just where the instance was assigned. Related: goto_definition, get_type_info. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await navigation.get_type_definition(app.pyright, file_path, line, character)
    _LOGGER.debug("get_type_definition count=%s", len(result))
    return result


async def get_folding_ranges(ctx: Context, file_path: str) -> list[FoldingRange]:
    """Get foldable code regions (functions, classes, if blocks, import groups) in a file. Use for chunked file analysis, generating table-of-contents views, or understanding file structure. Falls back to AST-based detection when LSP ranges are unavailable. Related: get_symbol_outline, selection_range."""
    app = get_current_backends()
    result = await navigation.get_folding_ranges(app.pyright, file_path)
    _LOGGER.debug("get_folding_ranges count=%s", len(result))
    return result


async def rename_symbol(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    new_name: str,
    apply: bool = False,
    include_diff: bool = False,
) -> RefactorResult:
    """Rename a symbol across the entire project — updates all references, imports, and usages. Use prepare_rename first to verify the symbol is renameable. Defaults to preview mode (apply=False); set apply=True to write changes. Set include_diff=True to get unified diffs in preview. Uses Pyright validation + rope execution. Related: prepare_rename, find_references. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.rename_symbol(
        app.pyright,
        app.rope,
        file_path,
        line,
        character,
        new_name,
        apply,
        include_diff,
    )
    _LOGGER.debug("rename_symbol edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def extract_method(
    ctx: Context,
    file_path: str,
    start_line: int,
    start_character: int,
    end_line: int,
    end_character: int,
    method_name: str,
    similar: bool = False,
    apply: bool = False,
) -> RefactorResult:
    """Extract a code selection into a new method, automatically detecting parameters and return values. Use when a block of code is too long or does a distinct subtask. Set similar=True to also replace other identical code fragments. Defaults to preview mode. Related: extract_variable, inline_variable. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.extract_method(
        app.pyright,
        app.rope,
        file_path,
        start_line,
        start_character,
        end_line,
        end_character,
        method_name,
        similar,
        apply,
    )
    _LOGGER.debug("extract_method edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def extract_variable(
    ctx: Context,
    file_path: str,
    start_line: int,
    start_character: int,
    end_line: int,
    end_character: int,
    variable_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Extract an expression into a named variable, replacing the original expression with the variable name. Use when a complex expression appears multiple times or needs a descriptive name for clarity. Defaults to preview mode. Related: extract_method, inline_variable. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.extract_variable(
        app.pyright,
        app.rope,
        file_path,
        start_line,
        start_character,
        end_line,
        end_character,
        variable_name,
        apply,
    )
    _LOGGER.debug("extract_variable edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def inline_variable(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Inline a variable — replace all usages with its assigned value and remove the assignment. Use when a variable adds no clarity and is only used to hold a temporary value. The inverse of extract_variable. Defaults to preview mode. Related: extract_variable, extract_method. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.inline_variable(app.pyright, app.rope, file_path, line, character, apply)
    _LOGGER.debug("inline_variable edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def move_symbol(
    ctx: Context,
    source_file: str,
    symbol_name: str,
    destination_file: str,
    apply: bool = False,
) -> RefactorResult:
    """Move a top-level symbol (function, class, variable) from one file to another, updating all imports across the project. Use when reorganizing module structure. Defaults to preview mode. Related: rename_symbol, module_to_package."""
    app = get_current_backends()
    result = await refactoring.move_symbol(app.pyright, app.rope, source_file, symbol_name, destination_file, apply)
    _LOGGER.debug("move_symbol edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def apply_code_action(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    action_title: str | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Apply a Pyright code action (quick fix, refactoring suggestion) at a location. Use when Pyright diagnostics suggest a fix — pass the action_title to select a specific action, or omit it to list available actions. Defaults to preview mode. Related: organize_imports, get_diagnostics. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.apply_code_action(app.pyright, file_path, line, character, action_title, apply)
    _LOGGER.debug("apply_code_action edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def organize_imports(
    ctx: Context,
    file_path: str,
    apply: bool = False,
    file_paths: list[str] | None = None,
) -> RefactorResult:
    """Sort and group imports according to PEP 8 conventions. Use to clean up messy import sections or as a post-refactoring step. Non-destructive — only reorders, never removes needed imports. Defaults to preview mode. Related: apply_code_action, get_diagnostics."""
    app = get_current_backends()
    result = await refactoring.organize_imports(app.pyright, file_path, apply, file_paths)
    _LOGGER.debug("organize_imports edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def format_code(
    ctx: Context,
    file_path: str,
    apply: bool = False,
    file_paths: list[str] | None = None,
) -> RefactorResult:
    """Run ruff-format on one or more files (respects project pyproject.toml / ruff.toml). Use to normalize formatting before commit or after a refactoring pass. Returns whole-file replace edits for changed files; already-formatted files are omitted. Defaults to preview mode. Related: organize_imports, get_diagnostics."""
    app = get_current_backends()
    result = await refactoring.format_code(app.pyright, file_path, apply, file_paths)
    _LOGGER.debug("format_code files=%s applied=%s", len(result.files_affected), result.applied)
    return result


async def apply_lint_fixes(
    ctx: Context,
    file_path: str,
    apply: bool = False,
    file_paths: list[str] | None = None,
    unsafe_fixes: bool = False,
) -> RefactorResult:
    """Run `ruff check --fix` on one or more files (respects project pyproject.toml / ruff.toml). Use to auto-resolve fixable diagnostics surfaced by `get_diagnostics` or `find_errors_static` — closes the auto-fix loop. Returns whole-file replace edits for changed files; files with no fixable issues are omitted. Set `unsafe_fixes=true` to also apply ruff's unsafe fixes. Defaults to preview mode. Related: format_code, organize_imports, get_diagnostics."""
    app = get_current_backends()
    result = await refactoring.apply_lint_fixes(app.pyright, file_path, apply, file_paths, unsafe_fixes)
    _LOGGER.debug("apply_lint_fixes files=%s applied=%s", len(result.files_affected), result.applied)
    return result


async def apply_type_annotations(
    ctx: Context,
    file_path: str,
    apply: bool = False,
    file_paths: list[str] | None = None,
) -> RefactorResult:
    """Materialize Pyright-inferred type hints into real source-level annotations. Pulls type-kind inlay hints across each target file and inserts them at the exact positions Pyright reports (return types, parameter annotations, variable annotations). Files where Pyright surfaces no type hints are silently dropped. Defaults to preview mode. Closes the loop with `get_inlay_hints` (read) and `get_type_coverage` (measure). Related: get_inlay_hints, get_type_coverage, format_code."""
    app = get_current_backends()
    result = await refactoring.apply_type_annotations(app.pyright, file_path, apply, file_paths)
    _LOGGER.debug(
        "apply_type_annotations edits=%s files=%s applied=%s",
        len(result.edits),
        len(result.files_affected),
        result.applied,
    )
    return result


async def convert_to_dataclass(
    ctx: Context,
    file_path: str,
    class_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Convert a behavior-free class constructor into standard-library `@dataclass` fields. Supports ordered direct `self.field = field` assignments, preserves parameter defaults and existing methods, and asks Pyright to infer missing field annotations. Unsupported behavioral constructors fail closed. Defaults to preview mode (`apply=false`). Related: apply_type_annotations, get_type_info, extract_superclass."""
    app = get_current_backends()
    result = await refactoring.convert_to_dataclass(app.pyright, file_path, class_name, apply)
    _LOGGER.debug(
        "convert_to_dataclass edits=%s files=%s applied=%s",
        len(result.edits),
        len(result.files_affected),
        result.applied,
    )
    return result


async def convert_to_pydantic(
    ctx: Context,
    file_path: str,
    class_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Convert one plain class with a fully typed keyword-only constructor into a Pydantic v2 model. The eligible constructor contains exactly one independent `ValueError` guard followed by ordered direct field assignments; inheritance, descriptors, positional construction, cross-field validation, mutable defaults, and broader behavior fail closed. Defaults to preview mode (`apply=false`) and refreshes diagnostics after apply. Related: convert_to_dataclass, convert_to_typeddict, diff_preview."""
    app = get_current_backends()
    result = await refactoring.convert_to_pydantic(app.pyright, file_path, class_name, apply)
    _LOGGER.debug(
        "convert_to_pydantic edits=%s files=%s applied=%s",
        len(result.edits),
        len(result.files_affected),
        result.applied,
    )
    return result


async def convert_to_typeddict(
    ctx: Context,
    file_path: str,
    function_name: str,
    typed_dict_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Convert a top-level function's consistent dict-literal returns into a generated `TypedDict`. Every return must use the same ordered string-identifier keys, and Pyright must infer one concrete type per field across all branches. Dynamic or inconsistent shapes fail closed. Defaults to preview mode (`apply=false`). Related: get_type_info, apply_type_annotations, convert_to_dataclass."""
    app = get_current_backends()
    result = await refactoring.convert_to_typeddict(
        app.pyright,
        file_path,
        function_name,
        typed_dict_name,
        apply,
    )
    _LOGGER.debug(
        "convert_to_typeddict edits=%s files=%s applied=%s",
        len(result.edits),
        len(result.files_affected),
        result.applied,
    )
    return result


async def convert_function_to_method(
    ctx: Context,
    file_path: str,
    function_name: str,
    class_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Move a top-level function into a plain class and rewrite every direct caller in the definition module from `function(instance, ...)` to `instance.function(...)`. The function's first positional parameter becomes the bound receiver without renaming, so body semantics and annotations stay intact. Cross-file or non-call references fail closed to prevent partial rewrites. Defaults to preview mode (`apply=false`). Related: find_references, convert_method_to_function, diff_preview."""
    app = get_current_backends()
    result = await refactoring.convert_function_to_method(
        app.pyright,
        app.jedi,
        file_path,
        function_name,
        class_name,
        apply,
    )
    _LOGGER.debug(
        "convert_function_to_method edits=%s files=%s applied=%s",
        len(result.edits),
        len(result.files_affected),
        result.applied,
    )
    return result


async def convert_method_to_function(
    ctx: Context,
    file_path: str,
    class_name: str,
    method_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Move a direct instance method from a plain class to module scope and rewrite every direct caller in that module from `instance.method(...)` to `method(instance, ...)`. The receiver parameter is preserved exactly; cross-file or non-call references fail closed to prevent partial rewrites. Defaults to preview mode (`apply=false`). Related: find_references, convert_function_to_method, diff_preview."""
    app = get_current_backends()
    result = await refactoring.convert_method_to_function(
        app.pyright,
        app.jedi,
        file_path,
        class_name,
        method_name,
        apply,
    )
    _LOGGER.debug(
        "convert_method_to_function edits=%s files=%s applied=%s",
        len(result.edits),
        len(result.files_affected),
        result.applied,
    )
    return result


async def docstring_sync(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    style: str = "auto",
    apply: bool = False,
) -> RefactorResult:
    """Synchronize one function signature with its existing Google, NumPy, or Sphinx docstring parameter fields. Point line/character at the function name. Positions are 0-based (line and character offsets, LSP convention). Auto-detection is the default; pass style='google', 'numpy', or 'sphinx' when adding the first parameter section. Existing descriptions are preserved, missing parameters are added, stale parameters are removed, and entries are reordered. Defaults to preview mode (`apply=false`). Related: change_signature, apply_type_annotations, diff_preview."""
    app = get_current_backends()
    result = await refactoring.docstring_sync(app.pyright, file_path, line, character, style, apply)
    _LOGGER.debug(
        "docstring_sync style=%s edits=%s files=%s applied=%s",
        style,
        len(result.edits),
        len(result.files_affected),
        result.applied,
    )
    return result


async def fix_circular_imports(
    ctx: Context,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Break runtime import cycles by moving only imports proven annotation-only behind `if TYPE_CHECKING:` and stringifying the affected annotations when needed. Mixed annotation/runtime imports and ambiguous source shapes are left unchanged. Scans the active workspace for runtime cycles; optionally restricts edits to `file_path` or `file_paths`. Defaults to preview mode (`apply=false`). Related: get_module_dependencies, get_diagnostics, diff_preview."""
    app = get_current_backends()
    result = await refactoring.fix_circular_imports(
        app.pyright,
        app.config,
        file_path,
        file_paths,
        apply,
    )
    _LOGGER.debug(
        "fix_circular_imports edits=%s files=%s applied=%s",
        len(result.edits),
        len(result.files_affected),
        result.applied,
    )
    return result


async def extract_superclass(
    ctx: Context,
    file_path: str,
    class_name: str,
    base_class_name: str,
    members: list[str],
    apply: bool = False,
) -> RefactorResult:
    """Pull a named subset of methods and class-level attributes up into a new base class, inserted immediately before the source class. Built on the LibCST foundation (rope has no ExtractSuperclass). Only plain `def` methods and class-level assignments hoist; @classmethod/@staticmethod/@property members, __slots__, and __init__ instance attributes are rejected with an error. Defaults to preview mode (apply=False). Related: extract_method, move_symbol."""
    app = get_current_backends()
    result = await refactoring.extract_superclass(app.pyright, file_path, class_name, base_class_name, members, apply)
    _LOGGER.debug(
        "extract_superclass edits=%s files=%s applied=%s", len(result.edits), len(result.files_affected), result.applied
    )
    return result


async def extract_class(
    ctx: Context,
    file_path: str,
    class_name: str,
    new_class_name: str,
    members: list[str],
    collaborator_attribute: str,
    apply: bool = False,
) -> RefactorResult:
    """Move direct constructor fields and plain instance methods into a new collaborator while preserving the source class API through field properties and method delegates. The collaborator is stored on the explicitly named source attribute. Unsafe shapes fail closed: moved methods may only use selected self members, and decorated/async/generator methods, decorated/slotted classes, duplicate bindings, and ambiguous assignments are rejected. Defaults to preview mode (apply=False). Related: extract_superclass, move_method, diff_preview."""
    app = get_current_backends()
    result = await refactoring.extract_class(
        app.pyright,
        file_path,
        class_name,
        new_class_name,
        members,
        collaborator_attribute,
        apply,
    )
    _LOGGER.debug(
        "extract_class edits=%s files=%s applied=%s",
        len(result.edits),
        len(result.files_affected),
        result.applied,
    )
    return result


async def expand_star_imports(
    ctx: Context,
    file_path: str,
    apply: bool = False,
) -> RefactorResult:
    """Replace ``from x import *`` with explicit named imports. Use to improve code quality and make dependencies explicit. Critical for large codebases where star imports hide the origin of names. Defaults to preview mode. Related: organize_imports, find_unused_imports."""
    app = get_current_backends()
    result = await refactoring.expand_star_imports(app.pyright, app.rope, file_path, apply)
    _LOGGER.debug("expand_star_imports edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def relatives_to_absolutes(
    ctx: Context,
    file_path: str,
    apply: bool = False,
) -> RefactorResult:
    """Convert all relative imports to absolute imports in a file. Use when migrating modules or enforcing absolute import style. Defaults to preview mode. Related: froms_to_imports, organize_imports."""
    app = get_current_backends()
    result = await refactoring.relatives_to_absolutes(app.pyright, app.rope, file_path, apply)
    _LOGGER.debug("relatives_to_absolutes edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def froms_to_imports(
    ctx: Context,
    file_path: str,
    apply: bool = False,
) -> RefactorResult:
    """Convert ``from module import name`` to ``import module`` style. Use to switch import convention or reduce namespace pollution. Defaults to preview mode. Related: relatives_to_absolutes, organize_imports."""
    app = get_current_backends()
    result = await refactoring.froms_to_imports(app.pyright, app.rope, file_path, apply)
    _LOGGER.debug("froms_to_imports edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def handle_long_imports(
    ctx: Context,
    file_path: str,
    apply: bool = False,
) -> RefactorResult:
    """Break long import lines per project preferences (maxdots, maxlength). Use to enforce line length limits in import sections. Defaults to preview mode. Related: organize_imports, expand_star_imports."""
    app = get_current_backends()
    result = await refactoring.handle_long_imports(app.pyright, app.rope, file_path, apply)
    _LOGGER.debug("handle_long_imports edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def autoimport_search(
    ctx: Context,
    name: str,
) -> list[ImportSuggestion]:
    """Search for importable names using rope's SQLite-backed AutoImport cache. Use for fast project-wide auto-import suggestions, especially in large projects. Complements suggest_imports with cached lookups. Related: suggest_imports, expand_star_imports."""
    app = get_current_backends()
    result = await refactoring.autoimport_search(app.rope, name)
    _LOGGER.debug("autoimport_search name=%s count=%s", name, len(result))
    return result


async def prepare_rename(ctx: Context, file_path: str, line: int, character: int) -> PrepareRenameResult | None:
    """Check if a symbol at a position can be renamed and return the editable range. Use before rename_symbol to verify the operation is valid and to get the current symbol name and range. Returns None if the position is not renameable. Related: rename_symbol, find_references. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.prepare_rename(app.pyright, file_path, line, character)
    _LOGGER.debug("prepare_rename valid=%s", result is not None)
    return result


async def introduce_parameter(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    parameter_name: str,
    default_value: str = "",
    apply: bool = False,
) -> RefactorResult:
    """Convert a local expression into a function parameter, adding it to the signature and updating all call sites with a default value. Use when you want to make a hardcoded value configurable. Defaults to preview mode. Related: change_signature, encapsulate_field. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.introduce_parameter(
        app.pyright,
        app.rope,
        file_path,
        line,
        character,
        parameter_name,
        default_value,
        apply,
    )
    _LOGGER.debug("introduce_parameter edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def encapsulate_field(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Wrap a class field with property getter/setter accessors, updating all direct field accesses. Use to add validation, logging, or lazy initialization to field access without changing callers. Defaults to preview mode. Related: introduce_parameter, local_to_field. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.encapsulate_field(app.pyright, app.rope, file_path, line, character, apply)
    _LOGGER.debug("encapsulate_field edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def change_signature(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    operations: list[SignatureOperation],
    apply: bool = False,
) -> RefactorResult:
    """Modify a function's signature — add, remove, reorder, or rename parameters — and update all call sites. Operations: 'add', 'remove', 'reorder', 'rename', 'inline_default', 'normalize'. Defaults to preview mode. Related: introduce_parameter, rename_symbol. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.change_signature(app.pyright, app.rope, file_path, line, character, operations, apply)
    _LOGGER.debug("change_signature edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def restructure(
    ctx: Context,
    pattern: str,
    goal: str,
    checks: dict[str, str] | None = None,
    imports: list[str] | None = None,
    file_path: str | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Apply pattern-based code transformations using rope's structural replace engine. Define a source pattern and a goal pattern to find-and-replace code structures. Use checks to constrain matches and imports to add needed imports. Defaults to preview mode. Related: structural_search (find without replace)."""
    app = get_current_backends()
    result = await refactoring.restructure(app.pyright, app.rope, pattern, goal, checks, imports, file_path, apply)
    _LOGGER.debug("restructure edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def use_function(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Find code blocks duplicating a function's body and replace them with calls to that function. Use to eliminate copy-paste duplication. Point to the function definition, and rope will find matching patterns across the project. Defaults to preview mode. Related: extract_method, restructure. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.use_function(app.pyright, app.rope, file_path, line, character, apply)
    _LOGGER.debug("use_function edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def introduce_factory(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    factory_name: str | None = None,
    global_factory: bool = True,
    apply: bool = False,
) -> RefactorResult:
    """Create a factory function that wraps a class constructor, updating all direct instantiations to use the factory. Use when you need to add indirection for dependency injection or when subclass selection logic is needed. Defaults to preview mode. Related: extract_method, method_object. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.introduce_factory(
        app.pyright,
        app.rope,
        file_path,
        line,
        character,
        factory_name,
        global_factory,
        apply,
    )
    _LOGGER.debug("introduce_factory edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def module_to_package(ctx: Context, file_path: str, apply: bool = False) -> RefactorResult:
    """Convert a single-file module into a package (directory with __init__.py), preserving all imports. Use when a module grows too large and needs to be split into submodules. Defaults to preview mode. Related: move_symbol."""
    app = get_current_backends()
    result = await refactoring.module_to_package(app.pyright, app.rope, file_path, apply)
    _LOGGER.debug("module_to_package edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def local_to_field(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Promote a local variable inside a method to an instance field (self.name), updating all usages within the class. Use when a computed value needs to be shared across methods. Defaults to preview mode. Related: encapsulate_field, extract_variable. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.local_to_field(app.pyright, app.rope, file_path, line, character, apply)
    _LOGGER.debug("local_to_field edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def method_object(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    classname: str | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Convert a method with complex logic into a callable object (functor class) with __call__. Use when a method has many local variables and would benefit from being its own class with fields. Defaults to preview mode. Related: extract_method, introduce_factory. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.method_object(app.pyright, app.rope, file_path, line, character, classname, apply)
    _LOGGER.debug("method_object edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def inline_method(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Inline a function/method body into all call sites and remove the original definition. Use when a method is trivial or called in only one place and adds unnecessary indirection. The inverse of extract_method. Defaults to preview mode. Related: inline_variable, extract_method. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.inline_method(app.pyright, app.rope, file_path, line, character, apply)
    _LOGGER.debug("inline_method edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def inline_parameter(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Remove a parameter by inlining its default value into the function body. Use when a parameter is always called with the same value and can be replaced with a constant. Position cursor on the parameter name in the function definition. Defaults to preview mode. Related: change_signature, introduce_parameter. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.inline_parameter(app.pyright, app.rope, file_path, line, character, apply)
    _LOGGER.debug("inline_parameter edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def move_method(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    destination_attr: str,
    apply: bool = False,
) -> RefactorResult:
    """Move a method from one class to another, creating a delegate in the original class. Use when a method uses another class's data more than its own. The destination_attr is the attribute name on the source class that references the target class instance. Defaults to preview mode. Related: move_symbol, extract_method. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.move_method(app.pyright, app.rope, file_path, line, character, destination_attr, apply)
    _LOGGER.debug("move_method edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def move_module(
    ctx: Context,
    source_path: str,
    destination_package: str,
    apply: bool = False,
) -> RefactorResult:
    """Move or rename an entire module or package, updating all imports across the project. Use when reorganizing package structure. The source_path is the module file to move; destination_package is the target package directory. Defaults to preview mode. Related: move_symbol, module_to_package."""
    app = get_current_backends()
    result = await refactoring.move_module(app.pyright, app.rope, source_path, destination_package, apply)
    _LOGGER.debug("move_module edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def generate_code(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    kind: str,
    apply: bool = False,
) -> RefactorResult:
    """Generate a missing class, function, variable, module, or package from a usage site. Use when code references a name that doesn't exist yet — rope creates a skeleton definition. The kind parameter must be one of: 'class', 'function', 'variable', 'module', 'package'. Defaults to preview mode. Related: extract_method, introduce_factory. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await refactoring.generate_code(app.pyright, app.rope, file_path, line, character, kind, apply)
    _LOGGER.debug("generate_code kind=%s edits=%s applied=%s", kind, len(result.edits), result.applied)
    return result


async def fix_module_names(ctx: Context, apply: bool = False) -> RefactorResult:
    """Batch-rename modules to conform to PEP 8 lowercase naming conventions, updating all imports. Use to enforce consistent module naming across the project. Defaults to preview mode. Related: rename_symbol, move_module."""
    app = get_current_backends()
    result = await refactoring.fix_module_names(app.pyright, app.rope, apply)
    _LOGGER.debug("fix_module_names edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def find_constructors(
    ctx: Context,
    class_name: str,
    file_path: str | None = None,
    limit: int | None = None,
) -> ConstructorSearchResult:
    """Find all places where a class is instantiated (constructor calls). Returns explicit scan_failures when files or reference lookups cannot be inspected. Use before refactoring a class to understand how it's created and with what arguments. Optionally scope to a single file. Related: find_references, type_hierarchy."""
    app = get_current_backends()
    result = await search.find_constructors(app.pyright, app.config, class_name, file_path, limit)
    log = _LOGGER.warning if result.scan_failures else _LOGGER.debug
    log(
        "find_constructors count=%s total=%s scan_failures=%s",
        len(result.items),
        result.total_count,
        len(result.scan_failures),
    )
    return result


async def search_symbols(ctx: Context, query: str, limit: int | None = None) -> SymbolSearchResult:
    """Search for symbols (functions, classes, variables) by name across the workspace. Use to locate a symbol when you know its name but not its file. Searches both Pyright and Jedi and reports partial-backend failures explicitly. Related: get_symbol_outline (structure-based), find_references (usage-based)."""
    app = get_current_backends()
    result = await search.search_symbols(app.pyright, app.jedi, query, limit)
    log = _LOGGER.warning if result.backend_failures else _LOGGER.debug
    log(
        "search_symbols count=%s backend_failures=%s",
        len(result.items),
        [f"{failure.backend}:{failure.error_type}" for failure in result.backend_failures],
    )
    return result


async def structural_search(
    ctx: Context,
    pattern: str,
    file_path: str | None = None,
    language: str = "python",
    limit: int | None = None,
) -> StructuralSearchResult:
    """Search for code patterns using LibCST matcher expressions. Use to find specific code structures (e.g., all try/except blocks, all calls to a specific function pattern). Patterns use the LibCST matcher DSL with m.* helpers. Check files_scanned in the response to distinguish "found nothing" from "failed to scan". Related: restructure (pattern-based replace), dead_code_detection."""
    app = get_current_backends()
    matches, files_scanned, scan_failures = await search.structural_search(
        app.config, pattern, file_path, language, limit
    )
    _LOGGER.debug(
        "structural_search language=%s matches=%s files_scanned=%s scan_failures=%s",
        language,
        len(matches),
        files_scanned,
        len(scan_failures),
    )
    return StructuralSearchResult(
        matches=matches,
        files_scanned=files_scanned,
        scan_failures=scan_failures,
    )


async def dead_code_detection(
    ctx: Context,
    file_path: str | None = None,
    exclude_patterns: list[str] | None = None,
    root_path: str | None = None,
    exclude_test_files: bool = True,
    file_paths: list[str] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> PaginatedDeadCode:
    """Find unreferenced functions, classes, and variables that may be dead code. Combines Pyright diagnostics (unused/not-accessed) with reference counting for module-level symbols. Set exclude_test_files=True to skip test files. Supports pagination via offset/limit. Returns confidence scores (high/medium/low). Related: get_diagnostics, find_references."""
    app = get_current_backends()
    result = await search.dead_code_detection(
        app.pyright,
        app.config,
        file_path,
        exclude_patterns,
        root_path,
        exclude_test_files,
        file_paths,
        offset,
        limit,
    )
    log = _LOGGER.warning if result.scan_failures else _LOGGER.debug
    log(
        "dead_code_detection count=%s total=%s scan_failures=%s",
        len(result.items),
        result.total_count,
        len(result.scan_failures),
    )
    return result


async def unused_symbol_sweep(
    ctx: Context,
    file_path: str | None = None,
    exclude_patterns: list[str] | None = None,
    root_path: str | None = None,
    exclude_test_files: bool = True,
    file_paths: list[str] | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> PaginatedDeadCode:
    """Audit the public export surface for symbols with zero cross-file references. Covers __all__-listed names (or all non-underscore module-level names when __all__ is absent) regardless of decoration, skipping externally-registered symbols (decorators containing mcp/tool). Complements dead_code_detection, which scopes to undecorated module-level symbols. May be slow on large codebases (one reference lookup per exported symbol). Supports pagination via offset/limit. Related: dead_code_detection, find_references."""
    app = get_current_backends()
    result = await search.unused_symbol_sweep(
        app.pyright,
        app.config,
        file_path,
        exclude_patterns,
        root_path,
        exclude_test_files,
        file_paths,
        offset,
        limit,
    )
    log = _LOGGER.warning if result.scan_failures else _LOGGER.debug
    log(
        "unused_symbol_sweep count=%s total=%s scan_failures=%s",
        len(result.items),
        result.total_count,
        len(result.scan_failures),
    )
    return result


async def suggest_imports(ctx: Context, symbol: str, file_path: str) -> list[ImportSuggestion]:
    """Suggest import statements for an unresolved symbol name. Use when a symbol is referenced but not imported — returns possible import statements from project and installed packages. Combines Pyright quick-fix suggestions with Jedi name search. Related: organize_imports, apply_code_action."""
    app = get_current_backends()
    result = await search.suggest_imports(app.pyright, app.jedi, symbol, file_path)
    _LOGGER.debug("suggest_imports symbol=%s count=%s", symbol, len(result))
    return result


async def code_metrics(
    ctx: Context,
    file_path: str,
    file_paths: list[str] | None = None,
) -> CodeMetricsResult:
    """Compute cyclomatic complexity, cognitive complexity, nesting depth, lines of code, and parameter count for all functions. Reports partial file scans through scan_failures. Use to identify complexity hotspots that need refactoring. Related: dead_code_detection, get_type_coverage."""
    _ = get_current_backends()
    result = await metrics.code_metrics(file_path, file_paths)
    log = _LOGGER.warning if result.scan_failures else _LOGGER.debug
    log(
        "code_metrics functions=%s max_cc=%s scan_failures=%s",
        result.total_functions,
        result.max_cyclomatic,
        len(result.scan_failures),
    )
    return result


async def get_module_dependencies(
    ctx: Context,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
) -> DependencyGraph:
    """Build an import dependency graph with circular dependency detection. Resolves absolute and package-relative imports to file paths, reports each cyclic strongly connected component deterministically, and exposes partial file scans through scan_failures. Related: get_coupling_metrics, check_layer_violations."""
    app = get_current_backends()
    result = await metrics.get_module_dependencies(app.config, file_path, file_paths)
    log = _LOGGER.warning if result.scan_failures else _LOGGER.debug
    log(
        "get_module_dependencies modules=%s deps=%s cycles=%s scan_failures=%s",
        len(result.modules),
        len(result.dependencies),
        len(result.circular_dependencies),
        len(result.scan_failures),
    )
    return result


async def find_duplicated_code(
    ctx: Context,
    file_path: str,
    file_paths: list[str] | None = None,
    min_lines: int = 3,
) -> DuplicateCodeResult:
    """Detect duplicated function bodies by normalizing AST and comparing hashes. Returns groups in items and exposes partial file scans through scan_failures. Use to find copy-paste code that should be refactored into shared functions. The min_lines parameter filters out trivially small functions. Related: use_function, extract_method."""
    _ = get_current_backends()
    result = await metrics.find_duplicated_code(file_path, file_paths, min_lines)
    log = _LOGGER.warning if result.scan_failures else _LOGGER.debug
    log("find_duplicated_code groups=%s scan_failures=%s", len(result.items), len(result.scan_failures))
    return result


async def get_type_coverage(
    ctx: Context,
    file_path: str,
    file_paths: list[str] | None = None,
) -> TypeCoverageReport:
    """Report type annotation completeness for function parameters and return types, including partial file scans in scan_failures. Use to audit type coverage and identify unannotated symbols. Related: get_type_hint_string, deep_type_inference."""
    _ = get_current_backends()
    result = await metrics.get_type_coverage(file_path, file_paths)
    log = _LOGGER.warning if result.scan_failures else _LOGGER.debug
    log(
        "get_type_coverage functions=%s return_pct=%s param_pct=%s scan_failures=%s",
        result.total_functions,
        result.return_coverage_pct,
        result.param_coverage_pct,
        len(result.scan_failures),
    )
    return result


async def get_coupling_metrics(
    ctx: Context,
    file_paths: list[str] | None = None,
) -> CouplingMetricsResult:
    """Compute afferent/efferent coupling and instability per module. Metrics are returned in items; dependency scan_failures remain visible. Ca = importers count, Ce = imports count, I = Ce/(Ca+Ce). Use to identify modules that are too coupled or too unstable. Related: get_module_dependencies, check_layer_violations."""
    app = get_current_backends()
    result = await metrics.get_coupling_metrics(app.config, file_paths=file_paths)
    log = _LOGGER.warning if result.scan_failures else _LOGGER.debug
    log("get_coupling_metrics modules=%s scan_failures=%s", len(result.items), len(result.scan_failures))
    return result


async def check_layer_violations(
    ctx: Context,
    layers: list[list[str]],
    file_paths: list[str] | None = None,
) -> LayerViolationResult:
    """Check import directions against declared layering rules. Violations are returned in items; partial file scans are returned in scan_failures. The layers parameter is ordered from highest (e.g., presentation) to lowest (e.g., domain). Flags imports from lower layers to higher layers. Related: get_module_dependencies, get_coupling_metrics."""
    app = get_current_backends()
    result = await metrics.check_layer_violations(app.config, layers, file_paths)
    log = _LOGGER.warning if result.scan_failures else _LOGGER.debug
    log("check_layer_violations violations=%s scan_failures=%s", len(result.items), len(result.scan_failures))
    return result


async def find_errors_static(ctx: Context, file_path: str) -> list[StaticError]:
    """Run rope's static analysis for bad name/attribute accesses. Complements Pyright diagnostics with rope's own analysis using finderrors. Use for an independent check of name resolution issues. Related: get_diagnostics, get_syntax_errors."""
    app = get_current_backends()
    result = await analysis.find_errors_static(app.rope, file_path)
    _LOGGER.debug("find_errors_static count=%s", len(result))
    return result


async def interface_conformance(
    ctx: Context,
    file_path: str,
    class_names: list[str],
) -> InterfaceComparison:
    """Compare class interfaces to detect implicit protocol conformance. Given class names in a file, extracts method signatures and reports common methods, unique methods, and signature mismatches. Use before extract_protocol to preview what the protocol will contain. Related: extract_protocol, type_hierarchy."""
    _ = get_current_backends()
    result = await metrics.interface_conformance(file_path, class_names)
    _LOGGER.debug("interface_conformance classes=%s common=%s", len(class_names), len(result.common_methods))
    return result


async def extract_protocol(
    ctx: Context,
    file_path: str,
    class_names: list[str],
    protocol_name: str = "GeneratedProtocol",
) -> ProtocolSource:
    """Generate a Protocol class from common methods of given classes. Reuses interface_conformance logic to find shared methods, then generates a copy-paste-ready Protocol definition. Related: interface_conformance, type_hierarchy."""
    _ = get_current_backends()
    result = await metrics.extract_protocol(file_path, class_names, protocol_name)
    _LOGGER.debug("extract_protocol methods=%s", len(result.methods))
    return result


async def get_module_public_api(ctx: Context, file_path: str) -> list[PublicAPIItem]:
    """Return only exported symbols from a module. Filters out _-prefixed names and respects __all__ if present. Use to understand a module's public interface without internal details. Related: get_symbol_outline, get_all_names."""
    _ = get_current_backends()
    result = await navigation.get_module_public_api(file_path)
    _LOGGER.debug("get_module_public_api count=%s", len(result))
    return result


async def diff_preview(ctx: Context, edits: list[TextEdit]) -> list[DiffPreview]:
    """Generate unified diff previews for a list of TextEdit objects. Use to visualize what changes will look like before applying them. Pass edits from any refactoring tool's preview output. Related: rename_symbol, extract_method (any tool returning TextEdit lists)."""
    _ = get_current_backends()
    result = await composite.diff_preview(edits)
    _LOGGER.debug("diff_preview files=%s", len(result))
    return result


async def refactor_transaction(ctx: Context, steps: list[dict[str, Any]]) -> TransactionResult:
    """Apply an ordered list of refactorings atomically under one change stack — commit all on success, roll back all on any failure. Each step is an object `{"tool": <name>, "args": {...}}`; steps run in order, and each is previewed against the RUNNING (partially-edited) source so later steps see earlier edits. Supported tools: rename_symbol, extract_method, extract_variable, inline_variable, inline_method (their `args` mirror each standalone tool, minus `apply`). Two failure contracts: (1) INPUT errors RAISE before anything is applied — an empty step list, a malformed step, an unsupported tool name, or a step missing `file_path` (all steps are validated up front). (2) EXECUTION failures RETURN a rolled-back result — if a step's refactoring raises mid-sequence or two steps touch overlapping character spans, the entire transaction is reverted and a TransactionResult with `applied=false`, `rolled_back=true` is returned: completed steps are marked `rolled_back`, the failing step `failed` with its `error` populated, the rest `skipped`. Disk is left byte-identical to the start in both cases. On success, returns per-step `applied` status plus a unified-diff summary of the committed changes. Related: begin_change_stack, commit_change_stack, diff_preview."""
    app = get_current_backends()
    result = await composite.refactor_transaction(app.rope, steps)
    _LOGGER.debug("refactor_transaction steps=%s applied=%s", len(result.steps), result.applied)
    return result


async def get_keyword_help(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
) -> DocumentationResult:
    """Documentation for Python keywords and operators. Use for keywords like yield, async, with and operators, not just names. Powered by Jedi. Related: get_documentation. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await app.jedi.get_help(file_path, line, character)
    _LOGGER.debug("get_keyword_help entries=%s", len(result.entries))
    return result


async def get_sub_definitions(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
) -> list[NameEntry]:
    """List sub-definitions of a name (e.g., methods of a class from a reference). Uses Jedi Name.defined_names(). Related: goto_definition, get_symbol_outline. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await app.jedi.get_sub_definitions(file_path, line, character)
    _LOGGER.debug("get_sub_definitions count=%s", len(result))
    return result


async def simulate_execution(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
) -> list[TypeInfo]:
    """Simulate calling a callable and return result types. Uses Jedi Name.execute(). Related: get_type_info, deep_type_inference. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await app.jedi.simulate_execute(file_path, line, character)
    _LOGGER.debug("simulate_execution count=%s", len(result))
    return result


async def list_environments(ctx: Context) -> list[EnvironmentInfo]:
    """Discover and list Python environments and virtualenvs. Uses Jedi environment detection. Related: get_context."""
    app = get_current_backends()
    result = await app.jedi.list_environments()
    _LOGGER.debug("list_environments count=%s", len(result))
    return result


async def project_search(
    ctx: Context,
    query: str,
    complete: bool = False,
) -> list[SymbolInfo]:
    """Project-wide semantic search using Jedi analysis engine. Complements workspace/symbol with Jedi Project.search(). Set complete=True for completion-style search. Related: search_symbols."""
    app = get_current_backends()
    result = await app.jedi.project_search(query, complete)
    _LOGGER.debug("project_search count=%s", len(result))
    return result


async def restart_server(ctx: Context) -> str:
    """Discard cached type info and restart Pyright analysis. Use when type information appears stale or after significant external file changes. Related: get_diagnostics."""
    app = get_current_backends()
    result = await app.pyright.restart_server()
    _LOGGER.debug("restart_server result=%s", result)
    return result


async def undo_refactoring(ctx: Context, count: int = 1) -> RefactorResult:
    """Undo the last refactoring operations. Uses Rope history. Related: redo_refactoring, get_refactoring_history."""
    app = get_current_backends()
    result = await app.rope.undo(count)
    _LOGGER.debug("undo_refactoring count=%s", count)
    return result


async def redo_refactoring(ctx: Context, count: int = 1) -> RefactorResult:
    """Redo previously undone refactoring operations. Uses Rope history. Related: undo_refactoring, get_refactoring_history."""
    app = get_current_backends()
    result = await app.rope.redo(count)
    _LOGGER.debug("redo_refactoring count=%s", count)
    return result


async def get_refactoring_history(ctx: Context) -> list[HistoryEntry]:
    """Get the refactoring change history. Returns entries with description, date, and affected files. Related: undo_refactoring, redo_refactoring."""
    app = get_current_backends()
    result = await app.rope.get_history()
    _LOGGER.debug("get_refactoring_history entries=%s", len(result))
    return result


async def begin_change_stack(ctx: Context) -> str:
    """Start an atomic change stack for chaining multiple refactorings. All changes are applied together on commit. Related: commit_change_stack, rollback_change_stack."""
    app = get_current_backends()
    result = await app.rope.begin_change_stack()
    _LOGGER.debug("begin_change_stack: %s", result)
    return result


async def commit_change_stack(ctx: Context) -> RefactorResult:
    """Commit and apply the current change stack atomically. Related: begin_change_stack, rollback_change_stack."""
    app = get_current_backends()
    result = await app.rope.commit_change_stack()
    _LOGGER.debug("commit_change_stack: applied=%s", result.applied)
    return result


async def rollback_change_stack(ctx: Context) -> str:
    """Discard the current change stack without applying. Related: begin_change_stack, commit_change_stack."""
    app = get_current_backends()
    result = await app.rope.rollback_change_stack()
    _LOGGER.debug("rollback_change_stack: %s", result)
    return result


async def multi_project_rename(
    ctx: Context,
    additional_roots: list[str],
    file_path: str,
    line: int,
    character: int,
    new_name: str,
    apply: bool = False,
) -> RefactorResult:
    """Rename a symbol across multiple Rope projects simultaneously. Provide additional workspace roots beyond the primary project. Related: rename_symbol. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    result = await app.rope.multi_project_rename(additional_roots, file_path, line, character, new_name, apply)
    _LOGGER.debug("multi_project_rename edits=%s applied=%s", len(result.edits), result.applied)
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  Registration table
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class ToolRecord:
    """One declarative tool registration.

    ``func`` is the *undecorated* delegate coroutine; ``annotations`` is the
    MCP :class:`ToolAnnotations` constant passed through verbatim per tool.
    """

    func: Callable[..., Awaitable[Any]]
    annotations: ToolAnnotations


# Advertising 80 or more tools in one profile leaves too little model
# selection headroom. New tools must fit this budget or trigger a deliberate
# profile split instead of raising a single global cap.
MAX_TOOLS_PER_PROFILE = 80

# The refactoring profile contains every mutating tool plus the read-only tools
# needed to scope, preview, validate, and recover a change safely. The analysis
# profile contains every read-only tool. Their union is the complete catalog.
_REFACTORING_SUPPORT_TOOLS = frozenset(
    {
        "autoimport_search",
        "dead_code_detection",
        "diff_preview",
        "find_errors_static",
        "find_references",
        "find_unused_imports",
        "get_diagnostics",
        "get_module_dependencies",
        "get_refactoring_history",
        "get_symbol_outline",
        "get_syntax_errors",
        "get_type_info",
        "get_workspace_diagnostics",
        "goto_definition",
        "list_environments",
        "prepare_rename",
        "search_symbols",
        "security_scan",
        "selection_range",
        "server_status",
        "structural_search",
        "suggest_imports",
        "test_impact_select",
    }
)


TOOL_RECORDS: tuple[ToolRecord, ...] = (
    ToolRecord(find_references, READ_ONLY_ANNOTATIONS),
    ToolRecord(find_type_users, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_type_info, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_documentation, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_signature_help, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_document_highlights, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_semantic_tokens, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_diagnostics, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_workspace_diagnostics, READ_ONLY_ANNOTATIONS),
    ToolRecord(deep_type_inference, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_type_hint_string, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_syntax_errors, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_context, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_all_names, READ_ONLY_ANNOTATIONS),
    ToolRecord(create_type_stubs, ADDITIVE_ANNOTATIONS),
    ToolRecord(check_type_stub_freshness, READ_ONLY_ANNOTATIONS),
    ToolRecord(call_hierarchy, READ_ONLY_ANNOTATIONS),
    ToolRecord(test_impact_select, READ_ONLY_ANNOTATIONS),
    ToolRecord(goto_definition, READ_ONLY_ANNOTATIONS),
    ToolRecord(type_hierarchy, READ_ONLY_ANNOTATIONS),
    ToolRecord(selection_range, READ_ONLY_ANNOTATIONS),
    ToolRecord(find_implementations, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_declaration, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_type_definition, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_folding_ranges, READ_ONLY_ANNOTATIONS),
    ToolRecord(rename_symbol, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(extract_method, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(convert_to_dataclass, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(convert_to_pydantic, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(convert_to_typeddict, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(convert_function_to_method, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(convert_method_to_function, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(docstring_sync, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(fix_circular_imports, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(extract_class, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(extract_superclass, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(extract_variable, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(inline_variable, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(move_symbol, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(apply_code_action, ADDITIVE_ANNOTATIONS),
    ToolRecord(organize_imports, ADDITIVE_ANNOTATIONS),
    ToolRecord(format_code, ADDITIVE_ANNOTATIONS),
    ToolRecord(apply_lint_fixes, ADDITIVE_ANNOTATIONS),
    ToolRecord(apply_type_annotations, ADDITIVE_ANNOTATIONS),
    ToolRecord(expand_star_imports, ADDITIVE_ANNOTATIONS),
    ToolRecord(relatives_to_absolutes, ADDITIVE_ANNOTATIONS),
    ToolRecord(froms_to_imports, ADDITIVE_ANNOTATIONS),
    ToolRecord(handle_long_imports, ADDITIVE_ANNOTATIONS),
    ToolRecord(autoimport_search, READ_ONLY_ANNOTATIONS),
    ToolRecord(prepare_rename, READ_ONLY_ANNOTATIONS),
    ToolRecord(introduce_parameter, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(encapsulate_field, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(change_signature, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(restructure, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(use_function, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(introduce_factory, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(module_to_package, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(local_to_field, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(method_object, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(inline_method, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(inline_parameter, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(move_method, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(move_module, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(generate_code, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(fix_module_names, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(find_constructors, READ_ONLY_ANNOTATIONS),
    ToolRecord(search_symbols, READ_ONLY_ANNOTATIONS),
    ToolRecord(structural_search, READ_ONLY_ANNOTATIONS),
    ToolRecord(dead_code_detection, READ_ONLY_ANNOTATIONS),
    ToolRecord(unused_symbol_sweep, READ_ONLY_ANNOTATIONS),
    ToolRecord(suggest_imports, READ_ONLY_ANNOTATIONS),
    ToolRecord(code_metrics, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_module_dependencies, READ_ONLY_ANNOTATIONS),
    ToolRecord(find_duplicated_code, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_type_coverage, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_coupling_metrics, READ_ONLY_ANNOTATIONS),
    ToolRecord(check_layer_violations, READ_ONLY_ANNOTATIONS),
    ToolRecord(find_errors_static, READ_ONLY_ANNOTATIONS),
    ToolRecord(interface_conformance, READ_ONLY_ANNOTATIONS),
    ToolRecord(extract_protocol, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_module_public_api, READ_ONLY_ANNOTATIONS),
    ToolRecord(diff_preview, READ_ONLY_ANNOTATIONS),
    ToolRecord(refactor_transaction, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(get_keyword_help, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_sub_definitions, READ_ONLY_ANNOTATIONS),
    ToolRecord(simulate_execution, READ_ONLY_ANNOTATIONS),
    ToolRecord(list_environments, READ_ONLY_ANNOTATIONS),
    ToolRecord(project_search, READ_ONLY_ANNOTATIONS),
    ToolRecord(restart_server, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(undo_refactoring, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(redo_refactoring, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(get_refactoring_history, READ_ONLY_ANNOTATIONS),
    ToolRecord(begin_change_stack, ADDITIVE_ANNOTATIONS),
    ToolRecord(commit_change_stack, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(rollback_change_stack, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(multi_project_rename, DESTRUCTIVE_ANNOTATIONS),
)


def _profile_includes(record: ToolRecord, profile: ToolProfile) -> bool:
    """Return whether *record* belongs to an advertised tool profile."""
    if profile == "analysis":
        return record.annotations.read_only_hint is True
    return record.annotations.read_only_hint is not True or record.func.__name__ in _REFACTORING_SUPPORT_TOOLS


def tool_names_for_profile(
    profile: ToolProfile,
    *,
    extra_records: tuple[ToolRecord, ...] = (),
) -> frozenset[str]:
    """Return the complete advertised name set for *profile*."""
    if profile not in TOOL_PROFILES:
        raise ValueError(f"Unknown tool profile: {profile!r}")
    records = (*TOOL_RECORDS, *extra_records)
    name_counts = Counter(record.func.__name__ for record in records)
    duplicates = sorted(name for name, count in name_counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate tool registrations: {', '.join(duplicates)}")
    return frozenset(record.func.__name__ for record in records if _profile_includes(record, profile))


def register_tools(
    mcp_instance: MCPServer,
    profile: ToolProfile,
    *,
    extra_records: tuple[ToolRecord, ...] = (),
) -> None:
    """Register the selected tool profile on *mcp_instance*.

    Applies ``tool_error_boundary`` (which preserves the delegate's name and
    signature via ``@wraps``) and then registers with the per-tool annotation
    constant. ``extra_records`` carries the non-delegating wrappers owned by
    ``server.py`` so one policy controls the complete advertised surface.

    Backend lookup and error handling come from ``tool_runtime`` so registry
    import order cannot depend on the server shell.
    """
    selected_names = tool_names_for_profile(profile, extra_records=extra_records)
    if len(selected_names) >= MAX_TOOLS_PER_PROFILE:
        raise ValueError(
            f"Tool profile {profile!r} advertises {len(selected_names)} tools; "
            f"must stay below the budget of {MAX_TOOLS_PER_PROFILE}"
        )

    for record in (*TOOL_RECORDS, *extra_records):
        if record.func.__name__ not in selected_names:
            continue
        mcp_instance.add_tool(
            tool_error_boundary(record.func),
            annotations=record.annotations,
        )
