"""FastMCP server shell and tool registration."""

from __future__ import annotations

import contextlib
import contextvars
import logging
import os
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import (
	CallHierarchyResult,
	CodeMetricsResult,
	CompletionItem,
	ConstructorSite,
	CouplingMetrics,
	DependencyGraph,
	Diagnostic,
	DiffPreview,
	DocumentationResult,
	DocumentHighlight,
	DuplicateGroup,
	EnvironmentInfo,
	FoldingRange,
	HistoryEntry,
	ImportSuggestion,
	InferredType,
	InlayHint,
	InterfaceComparison,
	LayerViolation,
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
	SecurityScanResult,
	SelectionRangeResult,
	SemanticToken,
	SignatureInfo,
	SignatureOperation,
	StaticError,
	StructuralSearchResult,
	SymbolInfo,
	SymbolOutlineItem,
	SyntaxErrorItem,
	TestCoverageMap,
	TextEdit,
	TypeCoverageReport,
	TypeHierarchyResult,
	TypeHintResult,
	TypeInfo,
	TypeUsersResult,
	UnusedImport,
)
from python_refactor_mcp.tools import analysis, composite, metrics, navigation, refactoring, search
from python_refactor_mcp.tools.metrics.security import security_scan as _security_scan
from python_refactor_mcp.tools.metrics.test_map import get_test_coverage_map as _get_test_coverage_map
from python_refactor_mcp.util.shared import apply_limit, validate_identifier, validate_workspace_path
from python_refactor_mcp.workspace_registry import WorkspaceBackends, WorkspaceRegistry

_READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
_ADDITIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

# Parameters that contain file paths requiring workspace boundary validation.
# Order is deliberate: when a tool accepts multiple path params, the first
# entry present in kwargs anchors workspace resolution. Source/subject paths
# come before destination paths so move/copy tools resolve to the source
# workspace rather than the destination.
_PATH_PARAMS: tuple[str, ...] = (
    "file_path",
    "source_file",
    "source_path",
    "root_path",
    "destination_file",
    "destination_package",
)
_LIST_PATH_PARAMS: tuple[str, ...] = ("file_paths",)

# Parameters that must be valid Python identifiers.
_IDENTIFIER_PARAMS: tuple[str, ...] = (
    "new_name", "method_name", "variable_name", "parameter_name", "factory_name", "classname",
)


# ── Multi-workspace context ──────────────────────────────────────────────

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class MultiWorkspaceContext:
	"""Lifespan context holding the workspace registry."""

	registry: WorkspaceRegistry
	cli_workspace_root: Path | None
	roots_fetched: bool = False


_workspace_root: Path | None = None
MCPContext = Context  # type: ignore[type-arg]

# ContextVar set by _tool_error_boundary so tool functions can read their
# resolved WorkspaceBackends without signature changes.
_current_backends: contextvars.ContextVar[WorkspaceBackends] = contextvars.ContextVar("_current_backends")


def _get_current_backends() -> WorkspaceBackends:
	"""Return the WorkspaceBackends for the current tool call.

	Set by ``_tool_error_boundary`` before the wrapped function runs.
	"""
	try:
		return _current_backends.get()
	except LookupError:
		raise RuntimeError(  # noqa: B904
			"No workspace backends available. "
			"Ensure the tool call was dispatched through _tool_error_boundary."
		)


def _get_multi_context(ctx: MCPContext) -> MultiWorkspaceContext:
	"""Extract MultiWorkspaceContext from the MCP lifespan context."""
	request_context = getattr(ctx, "request_context", None)
	if request_context is None:
		raise RuntimeError("MCP context is missing request_context.")

	lifespan_context = getattr(request_context, "lifespan_context", None)
	if not isinstance(lifespan_context, MultiWorkspaceContext):
		raise RuntimeError("MCP context is missing a valid MultiWorkspaceContext lifespan payload.")

	return lifespan_context


async def _maybe_fetch_roots(ctx: MCPContext, multi_ctx: MultiWorkspaceContext) -> None:
	"""Lazily fetch MCP roots from the client once per lifespan."""
	if multi_ctx.roots_fetched:
		return

	try:
		session = ctx.request_context.session
		roots_result = await session.list_roots()
		from python_refactor_mcp.util.paths import uri_to_path  # noqa: PLC0415

		root_paths = []
		for root in roots_result.roots:
			try:
				root_paths.append(Path(uri_to_path(str(root.uri))).resolve())
			except Exception:
				_LOGGER.warning("Failed to convert root URI: %s", root.uri)
		if root_paths:
			await multi_ctx.registry.set_roots(root_paths)
			_LOGGER.info("Updated workspace roots from MCP client: %s", root_paths)
	except Exception:
		_LOGGER.debug("MCP roots/list not available from client", exc_info=True)

	multi_ctx.roots_fetched = True


def _tool_error_boundary(  # noqa: UP047
	func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
	"""Convert backend errors into user-correctable tool errors.

	Resolves the correct workspace from file_path parameters, sets the
	per-call WorkspaceBackends ContextVar, validates path boundaries,
	and ensures identifier parameters are valid Python identifiers.
	"""

	@wraps(func)
	async def _wrapped(*args: Any, **kwargs: Any) -> Any:
		ctx = args[0] if args else kwargs.get("ctx")
		multi_ctx: MultiWorkspaceContext | None = None
		backends: WorkspaceBackends | None = None

		if ctx is not None:
			with contextlib.suppress(RuntimeError):
				multi_ctx = _get_multi_context(ctx)

		if multi_ctx is not None:
			assert ctx is not None
			registry = multi_ctx.registry

			# Lazy MCP roots fetch.
			await _maybe_fetch_roots(ctx, multi_ctx)

			# Find the primary file path from kwargs.
			primary_path: str | None = None
			for param_name in _PATH_PARAMS:
				value = kwargs.get(param_name)
				if isinstance(value, str):
					primary_path = value
					break
			if primary_path is None:
				for param_name in _LIST_PATH_PARAMS:
					values = kwargs.get(param_name)
					if isinstance(values, list) and values:
						first = next((v for v in values if isinstance(v, str)), None)
						if first is not None:
							primary_path = first
							break

			# Resolve workspace backends.
			if primary_path is not None:
				backends = await registry.get_backends(primary_path)
			else:
				# Fallback for tools without file_path params.
				backends = registry.get_most_recent()
				if backends is None and multi_ctx.cli_workspace_root is not None:
					backends = await registry.get_backends(
						str(multi_ctx.cli_workspace_root / "__fallback__"),
					)

		# Set the ContextVar for the tool function.
		token = _current_backends.set(backends) if backends is not None else None
		try:
			# Validate path parameters against the resolved workspace.
			if backends is not None:
				workspace_root = backends.config.workspace_root
				for param_name in _PATH_PARAMS:
					value = kwargs.get(param_name)
					if isinstance(value, str):
						kwargs[param_name] = validate_workspace_path(value, workspace_root)

				for param_name in _LIST_PATH_PARAMS:
					values = kwargs.get(param_name)
					if isinstance(values, list):
						kwargs[param_name] = [
							validate_workspace_path(v, workspace_root)
							for v in values
							if isinstance(v, str)
						]

			# Validate identifier parameters.
			for param_name in _IDENTIFIER_PARAMS:
				value = kwargs.get(param_name)
				if isinstance(value, str):
					validate_identifier(value, param_name)

			start = time.perf_counter()
			try:
				return await func(*args, **kwargs)
			except BackendError as exc:
				raise ValueError(str(exc)) from exc
			finally:
				elapsed_ms = (time.perf_counter() - start) * 1000
				if ctx is not None:
					with contextlib.suppress(Exception):
						await ctx.debug(f"{func.__name__} completed in {elapsed_ms:.1f}ms")
		finally:
			if token is not None:
				_current_backends.reset(token)

	return _wrapped


# ── Server lifecycle ─────────────────────────────────────────────────────


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncGenerator[MultiWorkspaceContext]:
	"""Create workspace registry and optionally pre-warm the CLI workspace."""
	_ = server
	max_ws = int(os.environ.get("MAX_WORKSPACES", "3"))
	registry = WorkspaceRegistry(max_workspaces=max_ws)

	# Pre-warm CLI workspace if provided.
	if _workspace_root is not None:
		await registry.set_roots([_workspace_root])
		# Eagerly initialize backends for the CLI workspace.
		await registry.get_backends(str(_workspace_root / "__init__.py"))

	try:
		yield MultiWorkspaceContext(
			registry=registry,
			cli_workspace_root=_workspace_root,
		)
	finally:
		await registry.shutdown_all()


_SERVER_INSTRUCTIONS = """\
Python Refactor MCP provides semantic code analysis and automated refactoring for Python projects.

Tool categories:
- **Analysis** (find_references, get_type_info, get_diagnostics, ...): Inspect code without modifying it.
- **Navigation** (goto_definition, call_hierarchy, get_symbol_outline, ...): Navigate code structure.
- **Refactoring** (rename_symbol, extract_method, move_symbol, ...): Transform code safely with preview support.
  All refactoring tools default to preview mode (apply=False). Set apply=True to write changes to disk.
- **Search** (search_symbols, dead_code_detection, structural_search, ...): Find patterns and issues.

Workflow tips:
- Use find_references before rename_symbol to understand impact scope.
- Use prepare_rename before rename_symbol to verify the symbol is renameable.
- Use get_diagnostics after applying refactorings to check for introduced errors.
- Use diff_preview to visualize pending TextEdit lists before applying them.
- Use get_type_info for type inspection; it combines Pyright and Jedi results.
"""

mcp = FastMCP(
	"Python Refactor",
	instructions=_SERVER_INSTRUCTIONS,
	lifespan=app_lifespan,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Analysis tools
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def find_references(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	include_declaration: bool = True,
	include_context: bool = False,
	limit: int | None = None,
) -> ReferenceResult:
	"""Find all references to a symbol across the workspace. Use when you need to understand how widely a function, class, or variable is used before renaming, moving, or deleting it. Returns locations from both Pyright and Jedi for comprehensive coverage. Set include_context=True to get surrounding source lines. Related: prepare_rename, rename_symbol."""
	app = _get_current_backends()
	result = await analysis.find_references(
		app.pyright, app.jedi, file_path, line, character, include_declaration, include_context, limit,
	)
	await ctx.debug(f"find_references source={result.source} count={result.total_count}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def find_type_users(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	kinds: list[str] | None = None,
	include_declaration: bool = False,
	limit: int | None = None,
) -> TypeUsersResult:
	"""Inverse of `find_references` scoped to a type — classify every reference site as `annotation` (type-hint position incl. subscripts like `list[Foo]`), `instantiation` (head of a `Foo(...)` call), `subclass` (in a `ClassDef.bases` list), or `other` (e.g. `isinstance(x, Foo)`, `Foo.classmethod`). Returns per-site classification plus aggregate `by_kind` counts. Pass `kinds=['annotation']` to filter; defaults to all four buckets. `include_declaration` defaults to False (the class definition itself is rarely an interesting type *use*). Related: find_references, type_hierarchy, find_implementations."""
	app = _get_current_backends()
	result = await analysis.find_type_users(
		app.pyright, app.jedi, file_path, line, character, kinds, include_declaration, limit,
	)
	await ctx.debug(
		f"find_type_users by_kind={result.by_kind} total={result.total_count} truncated={result.truncated}",
	)
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_type_info(ctx: MCPContext, file_path: str, line: int, character: int) -> TypeInfo:
	"""Infer the type of a symbol or expression at a source position. Use when you need to understand what type a variable holds, what a function returns, or what class an object is. Tries Pyright first with Jedi fallback for dynamic code. Related: get_documentation, get_type_hint_string."""
	app = _get_current_backends()
	result = await analysis.get_type_info(app.pyright, app.jedi, file_path, line, character)
	await ctx.debug(f"get_type_info source={result.source} type={result.type_string}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_completions(
	ctx: MCPContext, file_path: str, line: int, character: int, limit: int | None = None, fuzzy: bool = False,
) -> list[CompletionItem]:
	"""Get code completion candidates at a cursor position. Use when suggesting what a user might type next — returns available symbols, methods, and keywords at the given location. Sorted by label. Set fuzzy=True for fuzzy matching (e.g., 'ooa' matches 'foobar'). Related: get_signature_help (for call-site parameter info)."""
	app = _get_current_backends()
	if fuzzy:
		result = await app.jedi.get_completions(file_path, line, character, fuzzy=True)
		result, _ = apply_limit(result, limit)
	else:
		result = await analysis.get_completions(app.pyright, file_path, line, character, limit)
	await ctx.debug(f"get_completions count={len(result)} fuzzy={fuzzy}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_documentation(
	ctx: MCPContext, file_path: str, line: int, character: int, source: str | None = None,
) -> DocumentationResult:
	"""Get detailed documentation and docstrings for a symbol. Use when you need full API docs, function signatures, or module-level help. Powered by Jedi for rich dynamic analysis. Pass source to analyze in-memory content. Related: get_type_info (for type only), get_signature_help (for call-site params)."""
	app = _get_current_backends()
	result = await analysis.get_documentation(app.jedi, file_path, line, character, source)
	await ctx.debug(f"get_documentation entries={len(result.entries)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_signature_help(ctx: MCPContext, file_path: str, line: int, character: int) -> SignatureInfo | None:
	"""Get function signature help at a call site. Use when the cursor is inside a function call's parentheses to see parameter names, types, and which parameter is active. Tries Pyright first, falls back to Jedi for dynamic code. Related: get_completions, get_documentation."""
	app = _get_current_backends()
	result = await analysis.get_signature_help(app.pyright, file_path, line, character, jedi=app.jedi)
	await ctx.debug(f"get_signature_help found={result is not None}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_document_highlights(
	ctx: MCPContext, file_path: str, line: int, character: int,
) -> list[DocumentHighlight]:
	"""Highlight all read and write accesses of a symbol within a single file. Use to understand how a variable is used locally — which lines read it vs. which lines assign to it. Related: find_references (cross-file)."""
	app = _get_current_backends()
	result = await analysis.get_document_highlights(app.pyright, file_path, line, character)
	await ctx.debug(f"get_document_highlights count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_inlay_hints(
	ctx: MCPContext,
	file_path: str,
	start_line: int = 0,
	start_character: int = 0,
	end_line: int | None = None,
	end_character: int = 0,
) -> list[InlayHint]:
	"""Get inlay hints (inline type annotations, parameter names) for a file range. Use to visualize inferred types and parameter labels that aren't written in the source. Defaults to the full file when end_line is omitted. Related: get_type_info, get_semantic_tokens."""
	app = _get_current_backends()
	if end_line is None:
		try:
			line_count = len(Path(file_path).read_text(encoding="utf-8").splitlines())
		except (FileNotFoundError, OSError) as exc:
			raise ValueError(f"Cannot read file for line count: {exc}") from exc
		end_line = max(line_count, 0)
	result = await analysis.get_inlay_hints(
		app.pyright, file_path, start_line, start_character, end_line, end_character,
	)
	await ctx.debug(f"get_inlay_hints count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_semantic_tokens(ctx: MCPContext, file_path: str, limit: int | None = None) -> list[SemanticToken]:
	"""Get semantic token classifications for a file. Returns token type and modifier info for every symbol. Use for syntax-aware highlighting or to understand which tokens are namespaces, types, functions, etc. Can return large payloads — use limit to cap results. Related: get_inlay_hints."""
	app = _get_current_backends()
	result = await analysis.get_semantic_tokens(app.pyright, file_path, limit)
	await ctx.debug(f"get_semantic_tokens count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_diagnostics(
	ctx: MCPContext, file_path: str | None = None, severity_filter: str | None = None,
	limit: int | None = None, suppress_codes: list[str] | None = None,
	file_paths: list[str] | None = None,
) -> list[Diagnostic]:
	"""Get type-checking diagnostics (errors, warnings, hints) for one file, a batch of files, or the full project. Use after refactoring to verify no errors were introduced, or to audit code quality. Filter by severity_filter and suppress_codes to reduce noise. Related: get_workspace_diagnostics (aggregated counts)."""
	app = _get_current_backends()
	result = await analysis.get_diagnostics(
		app.pyright, file_path, severity_filter, limit, suppress_codes, file_paths,
	)
	await ctx.debug(f"get_diagnostics count={len(result)} severity_filter={severity_filter}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_workspace_diagnostics(
	ctx: MCPContext, root_path: str | None = None, suppress_codes: list[str] | None = None,
	file_paths: list[str] | None = None, offset: int = 0, limit: int | None = None,
) -> PaginatedDiagnosticSummary:
	"""Get aggregated diagnostic counts (errors, warnings, hints) per file across the workspace. Use for a high-level health overview of the codebase. Supports pagination via offset/limit. Related: get_diagnostics (detailed per-file diagnostics)."""
	app = _get_current_backends()
	result = await analysis.get_workspace_diagnostics(
		app.pyright, app.config, root_path, suppress_codes, file_paths, offset, limit,
	)
	await ctx.debug(f"get_workspace_diagnostics files={len(result.items)} total={result.total_count}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def deep_type_inference(
	ctx: MCPContext, file_path: str, line: int, character: int,
) -> list[InferredType]:
	"""Follow imports and statements to resolve final types at a position. Goes deeper than get_type_info by tracing through assignments and imports to their ultimate definitions. Use when get_type_info returns 'Unknown' for dynamic code. Related: get_type_info, get_type_hint_string."""
	app = _get_current_backends()
	result = await analysis.deep_type_inference(app.jedi, file_path, line, character)
	await ctx.debug(f"deep_type_inference count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_type_hint_string(
	ctx: MCPContext, file_path: str, line: int, character: int,
) -> list[TypeHintResult]:
	"""Return ready-to-use type annotation strings like ``Iterable[int]`` for a symbol. Use when adding missing type hints — provides copy-paste-ready annotations. Related: deep_type_inference, get_type_info."""
	app = _get_current_backends()
	result = await analysis.get_type_hint_string(app.jedi, file_path, line, character)
	await ctx.debug(f"get_type_hint_string count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_syntax_errors(ctx: MCPContext, file_path: str) -> list[SyntaxErrorItem]:
	"""Detect syntax errors via Jedi's parser. Complements Pyright diagnostics with an independent syntax check. Use to quickly find parse errors before running full type analysis. Related: get_diagnostics."""
	app = _get_current_backends()
	result = await analysis.get_syntax_errors(app.jedi, file_path)
	await ctx.debug(f"get_syntax_errors count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_context(
	ctx: MCPContext, file_path: str, line: int, character: int,
) -> ScopeContext | None:
	"""Return the enclosing function, class, or module scope at a position. Use to understand code structure and what scope a given line belongs to. Related: get_symbol_outline, call_hierarchy."""
	app = _get_current_backends()
	result = await analysis.get_context(app.jedi, file_path, line, character)
	await ctx.debug(f"get_context kind={result.kind if result else 'none'}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_all_names(
	ctx: MCPContext, file_path: str, all_scopes: bool = True, references: bool = False,
) -> list[NameEntry]:
	"""List all defined names in a file with optional nested scopes. Broader than get_symbol_outline — includes references and nested scopes when enabled. Use to audit all names used in a file. Related: get_symbol_outline, search_symbols."""
	app = _get_current_backends()
	result = await analysis.get_all_names(app.jedi, file_path, all_scopes, references)
	await ctx.debug(f"get_all_names count={len(result)}")
	return result


@mcp.tool(annotations=_ADDITIVE)
@_tool_error_boundary
async def create_type_stubs(ctx: MCPContext, package_name: str, output_dir: str | None = None) -> bool:
	"""Generate .pyi type stub files for a third-party package lacking type information. Use to improve type checking for untyped dependencies. The package_name is the import name (e.g., 'requests'). Optional output_dir specifies where to write stubs. Related: get_diagnostics, get_type_info."""
	app = _get_current_backends()
	result = await analysis.create_type_stubs(app.pyright, package_name, output_dir)
	await ctx.debug(f"create_type_stubs package={package_name} success={result}")
	return result


# ═══════════════════════════════════════════════════════════════════════════
#  Navigation tools
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def call_hierarchy(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	direction: str = "both",
	depth: int = 1,
	max_items: int | None = 200,
) -> CallHierarchyResult:
	"""Discover which functions call a given function (callers) and which functions it calls (callees). Use to understand call chains before refactoring. Set direction to 'callers', 'callees', or 'both'. Increase depth for deeper traversal. Related: type_hierarchy, find_references."""
	app = _get_current_backends()
	result = await navigation.call_hierarchy(app.pyright, file_path, line, character, direction, depth, max_items)
	await ctx.debug(
		f"call_hierarchy callers={len(result.callers)} callees={len(result.callees)} "
		f"depth={depth} direction={direction}"
	)
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def goto_definition(ctx: MCPContext, file_path: str, line: int, character: int) -> list[Location]:
	"""Jump to where a symbol is defined. Use when you encounter a function call, variable, or import and want to see its implementation. Follows imports to their source. Combines Pyright and Jedi for best coverage. Related: get_declaration, get_type_definition, find_implementations."""
	app = _get_current_backends()
	result = await navigation.goto_definition(app.pyright, app.jedi, file_path, line, character)
	await ctx.debug(f"goto_definition count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_symbol_outline(
	ctx: MCPContext,
	file_path: str | None = None,
	kind_filter: list[str] | None = None,
	name_pattern: str | None = None,
	limit: int | None = None,
	root_path: str | None = None,
	file_paths: list[str] | None = None,
	offset: int = 0,
) -> list[SymbolOutlineItem]:
	"""Get a hierarchical outline of classes, functions, and variables in a file or across the workspace. Use to understand code structure at a glance, find symbols by name pattern, or filter by kind (class, function, variable). Supports pagination via offset/limit. Related: search_symbols (name-based search), get_folding_ranges."""
	app = _get_current_backends()
	# Apply a sensible default limit for workspace-wide scans to prevent
	# excessive output (can produce millions of characters across many files).
	effective_limit = limit
	if effective_limit is None and file_path is None and file_paths is None:
		effective_limit = 500
	result = await navigation.get_symbol_outline(
		app.pyright, app.config, file_path, kind_filter, name_pattern, effective_limit, root_path,
		file_paths, offset,
	)
	await ctx.debug(f"get_symbol_outline count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def type_hierarchy(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	direction: str = "both",
	depth: int = 3,
	max_items: int | None = 200,
	class_name: str | None = None,
) -> TypeHierarchyResult:
	"""Discover class inheritance — supertypes (parents) and subtypes (children) of a class. Use to understand class hierarchies before refactoring or to find all implementations of a base class. Set direction to 'supertypes', 'subtypes', or 'both'. Related: call_hierarchy, find_implementations."""
	app = _get_current_backends()
	result = await navigation.type_hierarchy(
		app.pyright, file_path, line, character, direction, depth, max_items, class_name,
	)
	await ctx.debug(
		f"type_hierarchy supertypes={len(result.supertypes)} subtypes={len(result.subtypes)} "
		f"depth={depth} direction={direction}"
	)
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def selection_range(ctx: MCPContext, file_path: str, positions: list[Position]) -> list[SelectionRangeResult]:
	"""Get nested selection ranges (inner-most to outer-most scope) at source positions. Use for smart expand/shrink selection — progressively selects expression, statement, block, function, class, module. Related: get_folding_ranges."""
	app = _get_current_backends()
	result = await navigation.selection_range(app.pyright, file_path, positions)
	await ctx.debug(f"selection_range count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def find_implementations(ctx: MCPContext, file_path: str, line: int, character: int) -> list[Location]:
	"""Find concrete implementations of an abstract method or protocol. Use when you have a base class method and need to find all classes that implement it. Related: type_hierarchy, goto_definition."""
	app = _get_current_backends()
	result = await navigation.find_implementations(app.pyright, file_path, line, character)
	await ctx.debug(f"find_implementations count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_declaration(ctx: MCPContext, file_path: str, line: int, character: int) -> list[Location]:
	"""Navigate to the declaration site of a symbol (where it is first declared, not necessarily defined). For most Python code, this is equivalent to goto_definition. Related: goto_definition, get_type_definition."""
	app = _get_current_backends()
	result = await navigation.get_declaration(app.pyright, file_path, line, character)
	await ctx.debug(f"get_declaration count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_type_definition(ctx: MCPContext, file_path: str, line: int, character: int) -> list[Location]:
	"""Navigate to the type definition of a symbol (e.g., from a variable to its class definition). Use when you want to see the class behind an instance, not just where the instance was assigned. Related: goto_definition, get_type_info."""
	app = _get_current_backends()
	result = await navigation.get_type_definition(app.pyright, file_path, line, character)
	await ctx.debug(f"get_type_definition count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_folding_ranges(ctx: MCPContext, file_path: str) -> list[FoldingRange]:
	"""Get foldable code regions (functions, classes, if blocks, import groups) in a file. Use for chunked file analysis, generating table-of-contents views, or understanding file structure. Falls back to AST-based detection when LSP ranges are unavailable. Related: get_symbol_outline, selection_range."""
	app = _get_current_backends()
	result = await navigation.get_folding_ranges(app.pyright, file_path)
	await ctx.debug(f"get_folding_ranges count={len(result)}")
	return result


# ═══════════════════════════════════════════════════════════════════════════
#  Refactoring tools
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def rename_symbol(
	ctx: MCPContext, file_path: str, line: int, character: int, new_name: str,
	apply: bool = False, include_diff: bool = False,
) -> RefactorResult:
	"""Rename a symbol across the entire project — updates all references, imports, and usages. Use prepare_rename first to verify the symbol is renameable. Defaults to preview mode (apply=False); set apply=True to write changes. Set include_diff=True to get unified diffs in preview. Uses Pyright validation + rope execution. Related: prepare_rename, find_references."""
	app = _get_current_backends()
	result = await refactoring.rename_symbol(
		app.pyright, app.rope, file_path, line, character, new_name, apply, include_diff,
	)
	await ctx.debug(f"rename_symbol edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def extract_method(
	ctx: MCPContext,
	file_path: str,
	start_line: int,
	start_character: int,
	end_line: int,
	end_character: int,
	method_name: str,
	similar: bool = False,
	apply: bool = False,
) -> RefactorResult:
	"""Extract a code selection into a new method, automatically detecting parameters and return values. Use when a block of code is too long or does a distinct subtask. Set similar=True to also replace other identical code fragments. Defaults to preview mode. Related: extract_variable, inline_variable."""
	app = _get_current_backends()
	result = await refactoring.extract_method(
		app.pyright, app.rope, file_path, start_line, start_character,
		end_line, end_character, method_name, similar, apply,
	)
	await ctx.debug(f"extract_method edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def extract_variable(
	ctx: MCPContext,
	file_path: str,
	start_line: int,
	start_character: int,
	end_line: int,
	end_character: int,
	variable_name: str,
	apply: bool = False,
) -> RefactorResult:
	"""Extract an expression into a named variable, replacing the original expression with the variable name. Use when a complex expression appears multiple times or needs a descriptive name for clarity. Defaults to preview mode. Related: extract_method, inline_variable."""
	app = _get_current_backends()
	result = await refactoring.extract_variable(
		app.pyright, app.rope, file_path, start_line, start_character, end_line, end_character, variable_name, apply,
	)
	await ctx.debug(f"extract_variable edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def inline_variable(
	ctx: MCPContext, file_path: str, line: int, character: int, apply: bool = False,
) -> RefactorResult:
	"""Inline a variable — replace all usages with its assigned value and remove the assignment. Use when a variable adds no clarity and is only used to hold a temporary value. The inverse of extract_variable. Defaults to preview mode. Related: extract_variable, extract_method."""
	app = _get_current_backends()
	result = await refactoring.inline_variable(app.pyright, app.rope, file_path, line, character, apply)
	await ctx.debug(f"inline_variable edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def move_symbol(
	ctx: MCPContext, source_file: str, symbol_name: str, destination_file: str, apply: bool = False,
) -> RefactorResult:
	"""Move a top-level symbol (function, class, variable) from one file to another, updating all imports across the project. Use when reorganizing module structure. Defaults to preview mode. Related: rename_symbol, module_to_package."""
	app = _get_current_backends()
	result = await refactoring.move_symbol(app.pyright, app.rope, source_file, symbol_name, destination_file, apply)
	await ctx.debug(f"move_symbol edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_ADDITIVE)
@_tool_error_boundary
async def apply_code_action(
	ctx: MCPContext, file_path: str, line: int, character: int, action_title: str | None = None, apply: bool = False,
) -> RefactorResult:
	"""Apply a Pyright code action (quick fix, refactoring suggestion) at a location. Use when Pyright diagnostics suggest a fix — pass the action_title to select a specific action, or omit it to list available actions. Defaults to preview mode. Related: organize_imports, get_diagnostics."""
	app = _get_current_backends()
	result = await refactoring.apply_code_action(app.pyright, file_path, line, character, action_title, apply)
	await ctx.debug(f"apply_code_action edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_ADDITIVE)
@_tool_error_boundary
async def organize_imports(
	ctx: MCPContext, file_path: str, apply: bool = False, file_paths: list[str] | None = None,
) -> RefactorResult:
	"""Sort and group imports according to PEP 8 conventions. Use to clean up messy import sections or as a post-refactoring step. Non-destructive — only reorders, never removes needed imports. Defaults to preview mode. Related: apply_code_action, get_diagnostics."""
	app = _get_current_backends()
	result = await refactoring.organize_imports(app.pyright, file_path, apply, file_paths)
	await ctx.debug(f"organize_imports edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_ADDITIVE)
@_tool_error_boundary
async def format_code(
	ctx: MCPContext, file_path: str, apply: bool = False, file_paths: list[str] | None = None,
) -> RefactorResult:
	"""Run ruff-format on one or more files (respects project pyproject.toml / ruff.toml). Use to normalize formatting before commit or after a refactoring pass. Returns whole-file replace edits for changed files; already-formatted files are omitted. Defaults to preview mode. Related: organize_imports, get_diagnostics."""
	app = _get_current_backends()
	result = await refactoring.format_code(app.pyright, file_path, apply, file_paths)
	await ctx.debug(f"format_code files={len(result.files_affected)} applied={result.applied}")
	return result


@mcp.tool(annotations=_ADDITIVE)
@_tool_error_boundary
async def apply_lint_fixes(
	ctx: MCPContext,
	file_path: str,
	apply: bool = False,
	file_paths: list[str] | None = None,
	unsafe_fixes: bool = False,
) -> RefactorResult:
	"""Run `ruff check --fix` on one or more files (respects project pyproject.toml / ruff.toml). Use to auto-resolve fixable diagnostics surfaced by `get_diagnostics` or `find_errors_static` — closes the auto-fix loop. Returns whole-file replace edits for changed files; files with no fixable issues are omitted. Set `unsafe_fixes=true` to also apply ruff's unsafe fixes. Defaults to preview mode. Related: format_code, organize_imports, get_diagnostics."""
	app = _get_current_backends()
	result = await refactoring.apply_lint_fixes(app.pyright, file_path, apply, file_paths, unsafe_fixes)
	await ctx.debug(f"apply_lint_fixes files={len(result.files_affected)} applied={result.applied}")
	return result


@mcp.tool(annotations=_ADDITIVE)
@_tool_error_boundary
async def apply_type_annotations(
	ctx: MCPContext,
	file_path: str,
	apply: bool = False,
	file_paths: list[str] | None = None,
) -> RefactorResult:
	"""Materialize Pyright-inferred type hints into real source-level annotations. Pulls type-kind inlay hints across each target file and inserts them at the exact positions Pyright reports (return types, parameter annotations, variable annotations). Files where Pyright surfaces no type hints are silently dropped. Defaults to preview mode. Closes the loop with `get_inlay_hints` (read) and `get_type_coverage` (measure). Related: get_inlay_hints, get_type_coverage, format_code."""
	app = _get_current_backends()
	result = await refactoring.apply_type_annotations(app.pyright, file_path, apply, file_paths)
	await ctx.debug(
		f"apply_type_annotations edits={len(result.edits)} files={len(result.files_affected)} applied={result.applied}",
	)
	return result


@mcp.tool(annotations=_ADDITIVE)
@_tool_error_boundary
async def expand_star_imports(
	ctx: MCPContext, file_path: str, apply: bool = False,
) -> RefactorResult:
	"""Replace ``from x import *`` with explicit named imports. Use to improve code quality and make dependencies explicit. Critical for large codebases where star imports hide the origin of names. Defaults to preview mode. Related: organize_imports, find_unused_imports."""
	app = _get_current_backends()
	result = await refactoring.expand_star_imports(app.pyright, app.rope, file_path, apply)
	await ctx.debug(f"expand_star_imports edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_ADDITIVE)
@_tool_error_boundary
async def relatives_to_absolutes(
	ctx: MCPContext, file_path: str, apply: bool = False,
) -> RefactorResult:
	"""Convert all relative imports to absolute imports in a file. Use when migrating modules or enforcing absolute import style. Defaults to preview mode. Related: froms_to_imports, organize_imports."""
	app = _get_current_backends()
	result = await refactoring.relatives_to_absolutes(app.pyright, app.rope, file_path, apply)
	await ctx.debug(f"relatives_to_absolutes edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_ADDITIVE)
@_tool_error_boundary
async def froms_to_imports(
	ctx: MCPContext, file_path: str, apply: bool = False,
) -> RefactorResult:
	"""Convert ``from module import name`` to ``import module`` style. Use to switch import convention or reduce namespace pollution. Defaults to preview mode. Related: relatives_to_absolutes, organize_imports."""
	app = _get_current_backends()
	result = await refactoring.froms_to_imports(app.pyright, app.rope, file_path, apply)
	await ctx.debug(f"froms_to_imports edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_ADDITIVE)
@_tool_error_boundary
async def handle_long_imports(
	ctx: MCPContext, file_path: str, apply: bool = False,
) -> RefactorResult:
	"""Break long import lines per project preferences (maxdots, maxlength). Use to enforce line length limits in import sections. Defaults to preview mode. Related: organize_imports, expand_star_imports."""
	app = _get_current_backends()
	result = await refactoring.handle_long_imports(app.pyright, app.rope, file_path, apply)
	await ctx.debug(f"handle_long_imports edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def autoimport_search(
	ctx: MCPContext, name: str,
) -> list[ImportSuggestion]:
	"""Search for importable names using rope's SQLite-backed AutoImport cache. Use for fast project-wide auto-import suggestions, especially in large projects. Complements suggest_imports with cached lookups. Related: suggest_imports, expand_star_imports."""
	app = _get_current_backends()
	result = await refactoring.autoimport_search(app.rope, name)
	await ctx.debug(f"autoimport_search name={name} count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def prepare_rename(ctx: MCPContext, file_path: str, line: int, character: int) -> PrepareRenameResult | None:
	"""Check if a symbol at a position can be renamed and return the editable range. Use before rename_symbol to verify the operation is valid and to get the current symbol name and range. Returns None if the position is not renameable. Related: rename_symbol, find_references."""
	app = _get_current_backends()
	result = await refactoring.prepare_rename(app.pyright, file_path, line, character)
	await ctx.debug(f"prepare_rename valid={result is not None}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def introduce_parameter(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	parameter_name: str,
	default_value: str = "",
	apply: bool = False,
) -> RefactorResult:
	"""Convert a local expression into a function parameter, adding it to the signature and updating all call sites with a default value. Use when you want to make a hardcoded value configurable. Defaults to preview mode. Related: change_signature, encapsulate_field."""
	app = _get_current_backends()
	result = await refactoring.introduce_parameter(
		app.pyright, app.rope, file_path, line, character, parameter_name, default_value, apply,
	)
	await ctx.debug(f"introduce_parameter edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def encapsulate_field(
	ctx: MCPContext, file_path: str, line: int, character: int, apply: bool = False,
) -> RefactorResult:
	"""Wrap a class field with property getter/setter accessors, updating all direct field accesses. Use to add validation, logging, or lazy initialization to field access without changing callers. Defaults to preview mode. Related: introduce_parameter, local_to_field."""
	app = _get_current_backends()
	result = await refactoring.encapsulate_field(app.pyright, app.rope, file_path, line, character, apply)
	await ctx.debug(f"encapsulate_field edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def change_signature(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	operations: list[SignatureOperation],
	apply: bool = False,
) -> RefactorResult:
	"""Modify a function's signature — add, remove, reorder, or rename parameters — and update all call sites. Operations: 'add', 'remove', 'reorder', 'rename', 'inline_default', 'normalize'. Defaults to preview mode. Related: introduce_parameter, rename_symbol."""
	app = _get_current_backends()
	result = await refactoring.change_signature(app.pyright, app.rope, file_path, line, character, operations, apply)
	await ctx.debug(f"change_signature edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def restructure(
	ctx: MCPContext,
	pattern: str,
	goal: str,
	checks: dict[str, str] | None = None,
	imports: list[str] | None = None,
	file_path: str | None = None,
	apply: bool = False,
) -> RefactorResult:
	"""Apply pattern-based code transformations using rope's structural replace engine. Define a source pattern and a goal pattern to find-and-replace code structures. Use checks to constrain matches and imports to add needed imports. Defaults to preview mode. Related: structural_search (find without replace)."""
	app = _get_current_backends()
	result = await refactoring.restructure(app.pyright, app.rope, pattern, goal, checks, imports, file_path, apply)
	await ctx.debug(f"restructure edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def use_function(
	ctx: MCPContext, file_path: str, line: int, character: int, apply: bool = False,
) -> RefactorResult:
	"""Find code blocks duplicating a function's body and replace them with calls to that function. Use to eliminate copy-paste duplication. Point to the function definition, and rope will find matching patterns across the project. Defaults to preview mode. Related: extract_method, restructure."""
	app = _get_current_backends()
	result = await refactoring.use_function(app.pyright, app.rope, file_path, line, character, apply)
	await ctx.debug(f"use_function edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def introduce_factory(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	factory_name: str | None = None,
	global_factory: bool = True,
	apply: bool = False,
) -> RefactorResult:
	"""Create a factory function that wraps a class constructor, updating all direct instantiations to use the factory. Use when you need to add indirection for dependency injection or when subclass selection logic is needed. Defaults to preview mode. Related: extract_method, method_object."""
	app = _get_current_backends()
	result = await refactoring.introduce_factory(
		app.pyright, app.rope, file_path, line, character, factory_name, global_factory, apply,
	)
	await ctx.debug(f"introduce_factory edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def module_to_package(ctx: MCPContext, file_path: str, apply: bool = False) -> RefactorResult:
	"""Convert a single-file module into a package (directory with __init__.py), preserving all imports. Use when a module grows too large and needs to be split into submodules. Defaults to preview mode. Related: move_symbol."""
	app = _get_current_backends()
	result = await refactoring.module_to_package(app.pyright, app.rope, file_path, apply)
	await ctx.debug(f"module_to_package edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def local_to_field(
	ctx: MCPContext, file_path: str, line: int, character: int, apply: bool = False,
) -> RefactorResult:
	"""Promote a local variable inside a method to an instance field (self.name), updating all usages within the class. Use when a computed value needs to be shared across methods. Defaults to preview mode. Related: encapsulate_field, extract_variable."""
	app = _get_current_backends()
	result = await refactoring.local_to_field(app.pyright, app.rope, file_path, line, character, apply)
	await ctx.debug(f"local_to_field edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def method_object(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	classname: str | None = None,
	apply: bool = False,
) -> RefactorResult:
	"""Convert a method with complex logic into a callable object (functor class) with __call__. Use when a method has many local variables and would benefit from being its own class with fields. Defaults to preview mode. Related: extract_method, introduce_factory."""
	app = _get_current_backends()
	result = await refactoring.method_object(app.pyright, app.rope, file_path, line, character, classname, apply)
	await ctx.debug(f"method_object edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def inline_method(
	ctx: MCPContext, file_path: str, line: int, character: int, apply: bool = False,
) -> RefactorResult:
	"""Inline a function/method body into all call sites and remove the original definition. Use when a method is trivial or called in only one place and adds unnecessary indirection. The inverse of extract_method. Defaults to preview mode. Related: inline_variable, extract_method."""
	app = _get_current_backends()
	result = await refactoring.inline_method(app.pyright, app.rope, file_path, line, character, apply)
	await ctx.debug(f"inline_method edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def inline_parameter(
	ctx: MCPContext, file_path: str, line: int, character: int, apply: bool = False,
) -> RefactorResult:
	"""Remove a parameter by inlining its default value into the function body. Use when a parameter is always called with the same value and can be replaced with a constant. Position cursor on the parameter name in the function definition. Defaults to preview mode. Related: change_signature, introduce_parameter."""
	app = _get_current_backends()
	result = await refactoring.inline_parameter(app.pyright, app.rope, file_path, line, character, apply)
	await ctx.debug(f"inline_parameter edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def move_method(
	ctx: MCPContext, file_path: str, line: int, character: int, destination_attr: str, apply: bool = False,
) -> RefactorResult:
	"""Move a method from one class to another, creating a delegate in the original class. Use when a method uses another class's data more than its own. The destination_attr is the attribute name on the source class that references the target class instance. Defaults to preview mode. Related: move_symbol, extract_method."""
	app = _get_current_backends()
	result = await refactoring.move_method(app.pyright, app.rope, file_path, line, character, destination_attr, apply)
	await ctx.debug(f"move_method edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def move_module(
	ctx: MCPContext, source_path: str, destination_package: str, apply: bool = False,
) -> RefactorResult:
	"""Move or rename an entire module or package, updating all imports across the project. Use when reorganizing package structure. The source_path is the module file to move; destination_package is the target package directory. Defaults to preview mode. Related: move_symbol, module_to_package."""
	app = _get_current_backends()
	result = await refactoring.move_module(app.pyright, app.rope, source_path, destination_package, apply)
	await ctx.debug(f"move_module edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def generate_code(
	ctx: MCPContext, file_path: str, line: int, character: int, kind: str, apply: bool = False,
) -> RefactorResult:
	"""Generate a missing class, function, variable, module, or package from a usage site. Use when code references a name that doesn't exist yet — rope creates a skeleton definition. The kind parameter must be one of: 'class', 'function', 'variable', 'module', 'package'. Defaults to preview mode. Related: extract_method, introduce_factory."""
	app = _get_current_backends()
	result = await refactoring.generate_code(app.pyright, app.rope, file_path, line, character, kind, apply)
	await ctx.debug(f"generate_code kind={kind} edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def fix_module_names(ctx: MCPContext, apply: bool = False) -> RefactorResult:
	"""Batch-rename modules to conform to PEP 8 lowercase naming conventions, updating all imports. Use to enforce consistent module naming across the project. Defaults to preview mode. Related: rename_symbol, move_module."""
	app = _get_current_backends()
	result = await refactoring.fix_module_names(app.pyright, app.rope, apply)
	await ctx.debug(f"fix_module_names edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def argument_normalizer(
	ctx: MCPContext, file_path: str, line: int, character: int, apply: bool = False,
) -> RefactorResult:
	"""Normalize call-site arguments to match the function definition's parameter order. Use to clean up keyword arguments that are passed in a different order than the signature defines. Convenience wrapper over change_signature with op='normalize'. Defaults to preview mode. Related: change_signature, argument_default_inliner."""
	app = _get_current_backends()
	ops = [SignatureOperation(op="normalize")]
	result = await refactoring.change_signature(app.pyright, app.rope, file_path, line, character, ops, apply)
	await ctx.debug(f"argument_normalizer edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def argument_default_inliner(
	ctx: MCPContext, file_path: str, line: int, character: int, index: int, apply: bool = False,
) -> RefactorResult:
	"""Inline a parameter's default value into all call sites that omit it, then remove the default from the signature. Use to push defaults to callers before removing the parameter. The index is the 0-based parameter position. Convenience wrapper over change_signature with op='inline_default'. Defaults to preview mode. Related: change_signature, argument_normalizer."""
	app = _get_current_backends()
	ops = [SignatureOperation(op="inline_default", index=index)]
	result = await refactoring.change_signature(app.pyright, app.rope, file_path, line, character, ops, apply)
	await ctx.debug(f"argument_default_inliner edits={len(result.edits)} applied={result.applied}")
	return result


# ═══════════════════════════════════════════════════════════════════════════
#  Search tools
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def find_constructors(
	ctx: MCPContext, class_name: str, file_path: str | None = None, limit: int | None = None,
) -> list[ConstructorSite]:
	"""Find all places where a class is instantiated (constructor calls). Use before refactoring a class to understand how it's created and with what arguments. Optionally scope to a single file. Related: find_references, type_hierarchy."""
	app = _get_current_backends()
	result = await search.find_constructors(app.pyright, app.config, class_name, file_path, limit)
	await ctx.debug(f"find_constructors class={class_name} count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def search_symbols(ctx: MCPContext, query: str, limit: int | None = None) -> list[SymbolInfo]:
	"""Search for symbols (functions, classes, variables) by name across the workspace. Use to locate a symbol when you know its name but not its file. Searches both Pyright and Jedi for comprehensive results. Related: get_symbol_outline (structure-based), find_references (usage-based)."""
	app = _get_current_backends()
	result = await search.search_symbols(app.pyright, app.jedi, query, limit)
	await ctx.debug(f"search_symbols query={query} count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def structural_search(
	ctx: MCPContext, pattern: str, file_path: str | None = None, language: str = "python", limit: int | None = None,
) -> StructuralSearchResult:
	"""Search for code patterns using LibCST matcher expressions. Use to find specific code structures (e.g., all try/except blocks, all calls to a specific function pattern). Patterns use the LibCST matcher DSL with m.* helpers. Check files_scanned in the response to distinguish "found nothing" from "failed to scan". Related: restructure (pattern-based replace), dead_code_detection."""
	app = _get_current_backends()
	matches, files_scanned = await search.structural_search(app.config, pattern, file_path, language, limit)
	await ctx.debug(f"structural_search language={language} matches={len(matches)} files_scanned={files_scanned}")
	return StructuralSearchResult(matches=matches, files_scanned=files_scanned)


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def dead_code_detection(
	ctx: MCPContext, file_path: str | None = None,
	exclude_patterns: list[str] | None = None, root_path: str | None = None,
	exclude_test_files: bool = True, file_paths: list[str] | None = None,
	offset: int = 0, limit: int | None = None,
) -> PaginatedDeadCode:
	"""Find unreferenced functions, classes, and variables that may be dead code. Combines Pyright diagnostics (unused/not-accessed) with reference counting for module-level symbols. Set exclude_test_files=True to skip test files. Supports pagination via offset/limit. Returns confidence scores (high/medium/low). Related: get_diagnostics, find_references."""
	app = _get_current_backends()
	result = await search.dead_code_detection(
		app.pyright, app.config, file_path, exclude_patterns, root_path,
		exclude_test_files, file_paths, offset, limit,
	)
	await ctx.debug(f"dead_code_detection count={len(result.items)} total={result.total_count}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def suggest_imports(ctx: MCPContext, symbol: str, file_path: str) -> list[ImportSuggestion]:
	"""Suggest import statements for an unresolved symbol name. Use when a symbol is referenced but not imported — returns possible import statements from project and installed packages. Combines Pyright quick-fix suggestions with Jedi name search. Related: organize_imports, apply_code_action."""
	app = _get_current_backends()
	result = await search.suggest_imports(app.pyright, app.jedi, symbol, file_path)
	await ctx.debug(f"suggest_imports symbol={symbol} count={len(result)}")
	return result


# ═══════════════════════════════════════════════════════════════════════════
#  Metrics & Architecture tools
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def code_metrics(
	ctx: MCPContext, file_path: str, file_paths: list[str] | None = None,
) -> CodeMetricsResult:
	"""Compute cyclomatic complexity, cognitive complexity, nesting depth, lines of code, and parameter count for all functions. Use to identify complexity hotspots that need refactoring. Related: dead_code_detection, get_type_coverage."""
	_ = _get_current_backends()
	result = await metrics.code_metrics(file_path, file_paths)
	await ctx.debug(f"code_metrics functions={result.total_functions} max_cc={result.max_cyclomatic}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_module_dependencies(
	ctx: MCPContext, file_path: str | None = None, file_paths: list[str] | None = None,
) -> DependencyGraph:
	"""Build an import dependency graph with circular dependency detection. Parses ast.Import/ImportFrom nodes, resolves to file paths, and detects cycles via DFS. Related: get_coupling_metrics, check_layer_violations."""
	app = _get_current_backends()
	result = await metrics.get_module_dependencies(app.config, file_path, file_paths)
	await ctx.debug(f"get_module_dependencies modules={len(result.modules)} deps={len(result.dependencies)} cycles={len(result.circular_dependencies)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def find_unused_imports(
	ctx: MCPContext, file_path: str | None = None, file_paths: list[str] | None = None,
) -> list[UnusedImport]:
	"""Find unused imports using Pyright reportUnusedImport diagnostics with AST fallback. Use to clean up import sections before committing. Provide file_path for a single file, or file_paths for batch mode. Related: organize_imports, expand_star_imports."""
	app = _get_current_backends()
	if file_path is None and not file_paths:
		raise ValueError("Either file_path or file_paths must be provided.")
	effective_path = file_path if file_path is not None else file_paths[0]  # type: ignore[index]
	result = await metrics.find_unused_imports(app.pyright, effective_path, file_paths)
	await ctx.debug(f"find_unused_imports count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def find_duplicated_code(
	ctx: MCPContext, file_path: str, file_paths: list[str] | None = None, min_lines: int = 3,
) -> list[DuplicateGroup]:
	"""Detect duplicated function bodies by normalizing AST and comparing hashes. Use to find copy-paste code that should be refactored into shared functions. The min_lines parameter filters out trivially small functions. Related: use_function, extract_method."""
	_ = _get_current_backends()
	result = await metrics.find_duplicated_code(file_path, file_paths, min_lines)
	await ctx.debug(f"find_duplicated_code groups={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_type_coverage(
	ctx: MCPContext, file_path: str, file_paths: list[str] | None = None,
) -> TypeCoverageReport:
	"""Report type annotation completeness for function parameters and return types. Use to audit type coverage and identify unannotated symbols. Related: get_type_hint_string, deep_type_inference."""
	_ = _get_current_backends()
	result = await metrics.get_type_coverage(file_path, file_paths)
	await ctx.debug(f"get_type_coverage functions={result.total_functions} return_pct={result.return_coverage_pct} param_pct={result.param_coverage_pct}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_coupling_metrics(
	ctx: MCPContext, file_paths: list[str] | None = None,
) -> list[CouplingMetrics]:
	"""Compute afferent/efferent coupling and instability per module. Ca = importers count, Ce = imports count, I = Ce/(Ca+Ce). Use to identify modules that are too coupled or too unstable. Related: get_module_dependencies, check_layer_violations."""
	app = _get_current_backends()
	result = await metrics.get_coupling_metrics(app.config, file_paths=file_paths)
	await ctx.debug(f"get_coupling_metrics modules={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def check_layer_violations(
	ctx: MCPContext, layers: list[list[str]], file_paths: list[str] | None = None,
) -> list[LayerViolation]:
	"""Check import directions against declared layering rules. The layers parameter is ordered from highest (e.g., presentation) to lowest (e.g., domain). Flags imports from lower layers to higher layers. Related: get_module_dependencies, get_coupling_metrics."""
	app = _get_current_backends()
	result = await metrics.check_layer_violations(app.config, layers, file_paths)
	await ctx.debug(f"check_layer_violations violations={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def find_errors_static(ctx: MCPContext, file_path: str) -> list[StaticError]:
	"""Run rope's static analysis for bad name/attribute accesses. Complements Pyright diagnostics with rope's own analysis using finderrors. Use for an independent check of name resolution issues. Related: get_diagnostics, get_syntax_errors."""
	app = _get_current_backends()
	result = await analysis.find_errors_static(app.rope, file_path)
	await ctx.debug(f"find_errors_static count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def interface_conformance(
	ctx: MCPContext, file_path: str, class_names: list[str],
) -> InterfaceComparison:
	"""Compare class interfaces to detect implicit protocol conformance. Given class names in a file, extracts method signatures and reports common methods, unique methods, and signature mismatches. Use before extract_protocol to preview what the protocol will contain. Related: extract_protocol, type_hierarchy."""
	_ = _get_current_backends()
	result = await metrics.interface_conformance(file_path, class_names)
	await ctx.debug(f"interface_conformance classes={len(class_names)} common={len(result.common_methods)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def extract_protocol(
	ctx: MCPContext, file_path: str, class_names: list[str], protocol_name: str = "GeneratedProtocol",
) -> ProtocolSource:
	"""Generate a Protocol class from common methods of given classes. Reuses interface_conformance logic to find shared methods, then generates a copy-paste-ready Protocol definition. Related: interface_conformance, type_hierarchy."""
	_ = _get_current_backends()
	result = await metrics.extract_protocol(file_path, class_names, protocol_name)
	await ctx.debug(f"extract_protocol methods={len(result.methods)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_module_public_api(ctx: MCPContext, file_path: str) -> list[PublicAPIItem]:
	"""Return only exported symbols from a module. Filters out _-prefixed names and respects __all__ if present. Use to understand a module's public interface without internal details. Related: get_symbol_outline, get_all_names."""
	_ = _get_current_backends()
	result = await navigation.get_module_public_api(file_path)
	await ctx.debug(f"get_module_public_api count={len(result)}")
	return result


# ═══════════════════════════════════════════════════════════════════════════
#  Composite tools
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def diff_preview(ctx: MCPContext, edits: list[TextEdit]) -> list[DiffPreview]:
	"""Generate unified diff previews for a list of TextEdit objects. Use to visualize what changes will look like before applying them. Pass edits from any refactoring tool's preview output. Related: rename_symbol, extract_method (any tool returning TextEdit lists)."""
	_ = _get_current_backends()
	result = await composite.diff_preview(edits)
	await ctx.debug(f"diff_preview files={len(result)}")
	return result


# ═══════════════════════════════════════════════════════════════════════════
#  P4 Feature Tools
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_keyword_help(
	ctx: MCPContext, file_path: str, line: int, character: int,
) -> DocumentationResult:
	"""Documentation for Python keywords and operators. Use for keywords like yield, async, with and operators, not just names. Powered by Jedi. Related: get_documentation."""
	app = _get_current_backends()
	result = await app.jedi.get_help(file_path, line, character)
	await ctx.debug(f"get_keyword_help entries={len(result.entries)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_sub_definitions(
	ctx: MCPContext, file_path: str, line: int, character: int,
) -> list[NameEntry]:
	"""List sub-definitions of a name (e.g., methods of a class from a reference). Uses Jedi Name.defined_names(). Related: goto_definition, get_symbol_outline."""
	app = _get_current_backends()
	result = await app.jedi.get_sub_definitions(file_path, line, character)
	await ctx.debug(f"get_sub_definitions count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def simulate_execution(
	ctx: MCPContext, file_path: str, line: int, character: int,
) -> list[TypeInfo]:
	"""Simulate calling a callable and return result types. Uses Jedi Name.execute(). Related: get_type_info, deep_type_inference."""
	app = _get_current_backends()
	result = await app.jedi.simulate_execute(file_path, line, character)
	await ctx.debug(f"simulate_execution count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def list_environments(ctx: MCPContext) -> list[EnvironmentInfo]:
	"""Discover and list Python environments and virtualenvs. Uses Jedi environment detection. Related: get_context."""
	app = _get_current_backends()
	result = await app.jedi.list_environments()
	await ctx.debug(f"list_environments count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def project_search(
	ctx: MCPContext, query: str, complete: bool = False,
) -> list[SymbolInfo]:
	"""Project-wide semantic search using Jedi analysis engine. Complements workspace/symbol with Jedi Project.search(). Set complete=True for completion-style search. Related: search_symbols."""
	app = _get_current_backends()
	result = await app.jedi.project_search(query, complete)
	await ctx.debug(f"project_search count={len(result)}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def restart_server(ctx: MCPContext) -> str:
	"""Discard cached type info and restart Pyright analysis. Use when type information appears stale or after significant external file changes. Related: get_diagnostics."""
	app = _get_current_backends()
	result = await app.pyright.restart_server()
	await ctx.debug(f"restart_server result={result}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def undo_refactoring(ctx: MCPContext, count: int = 1) -> RefactorResult:
	"""Undo the last refactoring operations. Uses Rope history. Related: redo_refactoring, get_refactoring_history."""
	app = _get_current_backends()
	result = await app.rope.undo(count)
	await ctx.debug(f"undo_refactoring count={count}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def redo_refactoring(ctx: MCPContext, count: int = 1) -> RefactorResult:
	"""Redo previously undone refactoring operations. Uses Rope history. Related: undo_refactoring, get_refactoring_history."""
	app = _get_current_backends()
	result = await app.rope.redo(count)
	await ctx.debug(f"redo_refactoring count={count}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_refactoring_history(ctx: MCPContext) -> list[HistoryEntry]:
	"""Get the refactoring change history. Returns entries with description, date, and affected files. Related: undo_refactoring, redo_refactoring."""
	app = _get_current_backends()
	result = await app.rope.get_history()
	await ctx.debug(f"get_refactoring_history entries={len(result)}")
	return result


@mcp.tool(annotations=_ADDITIVE)
@_tool_error_boundary
async def begin_change_stack(ctx: MCPContext) -> str:
	"""Start an atomic change stack for chaining multiple refactorings. All changes are applied together on commit. Related: commit_change_stack, rollback_change_stack."""
	app = _get_current_backends()
	result = await app.rope.begin_change_stack()
	await ctx.debug(f"begin_change_stack: {result}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def commit_change_stack(ctx: MCPContext) -> RefactorResult:
	"""Commit and apply the current change stack atomically. Related: begin_change_stack, rollback_change_stack."""
	app = _get_current_backends()
	result = await app.rope.commit_change_stack()
	await ctx.debug(f"commit_change_stack: applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def rollback_change_stack(ctx: MCPContext) -> str:
	"""Discard the current change stack without applying. Related: begin_change_stack, commit_change_stack."""
	app = _get_current_backends()
	result = await app.rope.rollback_change_stack()
	await ctx.debug(f"rollback_change_stack: {result}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def multi_project_rename(
	ctx: MCPContext,
	additional_roots: list[str],
	file_path: str,
	line: int,
	character: int,
	new_name: str,
	apply: bool = False,
) -> RefactorResult:
	"""Rename a symbol across multiple Rope projects simultaneously. Provide additional workspace roots beyond the primary project. Related: rename_symbol."""
	app = _get_current_backends()
	result = await app.rope.multi_project_rename(additional_roots, file_path, line, character, new_name, apply)
	await ctx.debug(f"multi_project_rename edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_test_coverage_map(
	ctx: MCPContext,
	file_path: str | None = None,
	file_paths: list[str] | None = None,
) -> TestCoverageMap:
	"""Map source symbols to test references. Shows which functions/classes have test coverage. Related: find_references, dead_code_detection."""
	app = _get_current_backends()
	result = await _get_test_coverage_map(app.pyright, file_path, file_paths)
	await ctx.debug(f"get_test_coverage_map total={result.total_symbols} covered={result.covered_count}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def security_scan(
	ctx: MCPContext,
	file_path: str | None = None,
	file_paths: list[str] | None = None,
) -> SecurityScanResult:
	"""AST-based security scan for common Python vulnerabilities (eval, exec, shell injection, pickle, etc.). Related: get_diagnostics, dead_code_detection."""
	_ = _get_current_backends()
	result = await _security_scan(file_path, file_paths)
	await ctx.debug(f"security_scan files={result.files_scanned} findings={result.total_findings}")
	return result


# ═══════════════════════════════════════════════════════════════════════════
#  Server entrypoint
# ═══════════════════════════════════════════════════════════════════════════


def run_server(workspace_root: str | None = None) -> None:
	"""Start the FastMCP server using stdio transport.

	If *workspace_root* is provided, backends for that workspace are
	eagerly initialized at startup.  If omitted, the server starts cold
	and discovers workspaces dynamically from MCP roots or file_path
	parameters on the first tool call.
	"""
	global _workspace_root  # noqa: PLW0603
	_workspace_root = Path(workspace_root).resolve() if workspace_root else None
	mcp.run()
