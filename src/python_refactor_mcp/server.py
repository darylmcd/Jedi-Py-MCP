"""FastMCP server shell and tool registration for Stage 1."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from python_refactor_mcp.backends.jedi_backend import JediBackend
from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient
from python_refactor_mcp.backends.rope_backend import RopeBackend
from python_refactor_mcp.config import ServerConfig, discover_config
from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import (
	CallHierarchyResult,
	CompletionItem,
	ConstructorSite,
	DeadCodeItem,
	Diagnostic,
	DiagnosticSummary,
	DiffPreview,
	DocumentationResult,
	DocumentHighlight,
	FoldingRange,
	ImportSuggestion,
	InlayHint,
	Location,
	Position,
	PrepareRenameResult,
	RefactorResult,
	ReferenceResult,
	SelectionRangeResult,
	SemanticToken,
	SignatureInfo,
	SignatureOperation,
	StructuralMatch,
	SymbolInfo,
	SymbolOutlineItem,
	TextEdit,
	TypeHierarchyResult,
	TypeInfo,
)
from python_refactor_mcp.tools.analysis import (
	find_references as analysis_find_references,
)
from python_refactor_mcp.tools.analysis import (
	get_call_signatures_fallback as analysis_get_call_signatures_fallback,
)
from python_refactor_mcp.tools.analysis import get_completions as analysis_get_completions
from python_refactor_mcp.tools.analysis import (
	get_diagnostics as analysis_get_diagnostics,
)
from python_refactor_mcp.tools.analysis import get_document_highlights as analysis_get_document_highlights
from python_refactor_mcp.tools.analysis import get_documentation as analysis_get_documentation
from python_refactor_mcp.tools.analysis import get_hover_info as analysis_get_hover_info
from python_refactor_mcp.tools.analysis import get_inlay_hints as analysis_get_inlay_hints
from python_refactor_mcp.tools.analysis import get_semantic_tokens as analysis_get_semantic_tokens
from python_refactor_mcp.tools.analysis import get_signature_help as analysis_get_signature_help
from python_refactor_mcp.tools.analysis import get_type_info as analysis_get_type_info
from python_refactor_mcp.tools.analysis import get_workspace_diagnostics as analysis_get_workspace_diagnostics
from python_refactor_mcp.tools.composite import diff_preview as composite_diff_preview
from python_refactor_mcp.tools.composite import smart_rename as composite_smart_rename
from python_refactor_mcp.tools.navigation import call_hierarchy as navigation_call_hierarchy
from python_refactor_mcp.tools.navigation import find_implementations as navigation_find_implementations
from python_refactor_mcp.tools.navigation import get_declaration as navigation_get_declaration
from python_refactor_mcp.tools.navigation import get_folding_ranges as navigation_get_folding_ranges
from python_refactor_mcp.tools.navigation import get_symbol_outline as navigation_get_symbol_outline
from python_refactor_mcp.tools.navigation import get_type_definition as navigation_get_type_definition
from python_refactor_mcp.tools.navigation import goto_definition as navigation_goto_definition
from python_refactor_mcp.tools.navigation import selection_range as navigation_selection_range
from python_refactor_mcp.tools.navigation import type_hierarchy as navigation_type_hierarchy
from python_refactor_mcp.tools.refactoring import apply_code_action as refactoring_apply_code_action
from python_refactor_mcp.tools.refactoring import change_signature as refactoring_change_signature
from python_refactor_mcp.tools.refactoring import encapsulate_field as refactoring_encapsulate_field
from python_refactor_mcp.tools.refactoring import extract_method as refactoring_extract_method
from python_refactor_mcp.tools.refactoring import extract_variable as refactoring_extract_variable
from python_refactor_mcp.tools.refactoring import inline_variable as refactoring_inline_variable
from python_refactor_mcp.tools.refactoring import introduce_factory as refactoring_introduce_factory
from python_refactor_mcp.tools.refactoring import introduce_parameter as refactoring_introduce_parameter
from python_refactor_mcp.tools.refactoring import local_to_field as refactoring_local_to_field
from python_refactor_mcp.tools.refactoring import method_object as refactoring_method_object
from python_refactor_mcp.tools.refactoring import module_to_package as refactoring_module_to_package
from python_refactor_mcp.tools.refactoring import move_symbol as refactoring_move_symbol
from python_refactor_mcp.tools.refactoring import organize_imports as refactoring_organize_imports
from python_refactor_mcp.tools.refactoring import prepare_rename as refactoring_prepare_rename
from python_refactor_mcp.tools.refactoring import rename_symbol as refactoring_rename_symbol
from python_refactor_mcp.tools.refactoring import restructure as refactoring_restructure
from python_refactor_mcp.tools.refactoring import use_function as refactoring_use_function
from python_refactor_mcp.tools.search import dead_code_detection as search_dead_code_detection
from python_refactor_mcp.tools.search import find_constructors as search_find_constructors
from python_refactor_mcp.tools.search import search_symbols as search_search_symbols
from python_refactor_mcp.tools.search import structural_search as search_structural_search
from python_refactor_mcp.tools.search import suggest_imports as search_suggest_imports

_READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)


@dataclass(slots=True)
class AppContext:
	"""Application lifespan context shared by all MCP tools."""

	pyright: PyrightLSPClient
	jedi: JediBackend
	rope: RopeBackend
	config: ServerConfig


_workspace_root: Path | None = None
MCPContext = Context  # type: ignore[type-arg]


def _tool_error_boundary(  # noqa: UP047
	func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
	"""Convert backend errors into user-correctable tool errors."""

	@wraps(func)
	async def _wrapped(*args: Any, **kwargs: Any) -> Any:
		try:
			return await func(*args, **kwargs)
		except BackendError as exc:
			raise ValueError(str(exc)) from exc

	return _wrapped


def _get_workspace_root() -> Path:
	"""Resolve the workspace root configured by the CLI entrypoint."""
	if _workspace_root is None:
		return Path.cwd().resolve()
	return _workspace_root


def _get_app_context(ctx: MCPContext) -> AppContext:
	"""Extract and validate the lifespan app context from a tool context object."""
	request_context = getattr(ctx, "request_context", None)
	if request_context is None:
		raise RuntimeError("MCP context is missing request_context.")

	lifespan_context = getattr(request_context, "lifespan_context", None)
	if not isinstance(lifespan_context, AppContext):
		raise RuntimeError("MCP context is missing a valid AppContext lifespan payload.")

	return lifespan_context


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
	"""Create and dispose of backend resources for MCP tool calls."""
	_ = server
	config = discover_config(_get_workspace_root())
	pyright = PyrightLSPClient(config)
	jedi_backend = JediBackend(config)
	rope_backend = RopeBackend(config)

	await pyright.start()
	jedi_backend.initialize()
	rope_backend.initialize()

	try:
		yield AppContext(
			pyright=pyright,
			jedi=jedi_backend,
			rope=rope_backend,
			config=config,
		)
	finally:
		await pyright.shutdown()
		rope_backend.close()


mcp = FastMCP("Python Refactor", lifespan=app_lifespan)


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
	"""Find symbol references for the provided source location."""
	app = _get_app_context(ctx)
	result = await analysis_find_references(
		app.pyright,
		app.jedi,
		file_path,
		line,
		character,
		include_declaration,
		include_context,
		limit,
	)
	await ctx.debug(f"find_references source={result.source} count={result.total_count}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_type_info(ctx: MCPContext, file_path: str, line: int, character: int) -> TypeInfo:
	"""Get type information for the provided source location."""
	app = _get_app_context(ctx)
	result = await analysis_get_type_info(app.pyright, app.jedi, file_path, line, character)
	await ctx.debug(f"get_type_info source={result.source} type={result.type_string}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_hover_info(ctx: MCPContext, file_path: str, line: int, character: int) -> TypeInfo:
	"""Get hover-style type and documentation information for a source location."""
	app = _get_app_context(ctx)
	result = await analysis_get_hover_info(app.pyright, app.jedi, file_path, line, character)
	await ctx.debug(f"get_hover_info source={result.source} type={result.type_string}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_completions(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	limit: int | None = None,
) -> list[CompletionItem]:
	"""Get completion candidates for a source location."""
	app = _get_app_context(ctx)
	result = await analysis_get_completions(app.pyright, file_path, line, character, limit)
	await ctx.debug(f"get_completions count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_documentation(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	source: str | None = None,
) -> DocumentationResult:
	"""Get detailed symbol documentation/help for a source location."""
	app = _get_app_context(ctx)
	result = await analysis_get_documentation(app.jedi, file_path, line, character, source)
	await ctx.debug(f"get_documentation entries={len(result.entries)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_signature_help(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
) -> SignatureInfo | None:
	"""Get active signature help for a call site."""
	app = _get_app_context(ctx)
	result = await analysis_get_signature_help(app.pyright, file_path, line, character)
	await ctx.debug(f"get_signature_help found={result is not None}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_call_signatures_fallback(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
) -> SignatureInfo | None:
	"""Get Jedi signature-help fallback for dynamic call sites."""
	app = _get_app_context(ctx)
	result = await analysis_get_call_signatures_fallback(app.jedi, file_path, line, character)
	await ctx.debug(f"get_call_signatures_fallback found={result is not None}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_document_highlights(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
) -> list[DocumentHighlight]:
	"""Get read/write highlights for a symbol within a single file."""
	app = _get_app_context(ctx)
	result = await analysis_get_document_highlights(app.pyright, file_path, line, character)
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
	"""Get inlay hints for a file range; defaults to full file when end_line is omitted."""
	app = _get_app_context(ctx)
	if end_line is None:
		line_count = len(Path(file_path).read_text(encoding="utf-8").splitlines())
		end_line = max(line_count, 0)
	result = await analysis_get_inlay_hints(
		app.pyright,
		file_path,
		start_line,
		start_character,
		end_line,
		end_character,
	)
	await ctx.debug(f"get_inlay_hints count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_semantic_tokens(ctx: MCPContext, file_path: str) -> list[SemanticToken]:
	"""Get semantic token classifications for a file."""
	app = _get_app_context(ctx)
	result = await analysis_get_semantic_tokens(app.pyright, file_path)
	await ctx.debug(f"get_semantic_tokens count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_diagnostics(
	ctx: MCPContext,
	file_path: str | None = None,
	severity_filter: str | None = None,
	limit: int | None = None,
) -> list[Diagnostic]:
	"""Get diagnostics for a file or for the full workspace."""
	app = _get_app_context(ctx)
	result = await analysis_get_diagnostics(app.pyright, file_path, severity_filter, limit)
	await ctx.debug(f"get_diagnostics count={len(result)} severity_filter={severity_filter}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_workspace_diagnostics(ctx: MCPContext) -> list[DiagnosticSummary]:
	"""Get aggregated diagnostic counts for the full workspace."""
	app = _get_app_context(ctx)
	result = await analysis_get_workspace_diagnostics(app.pyright, app.config)
	await ctx.debug(f"get_workspace_diagnostics files={len(result)}")
	return result


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
	"""Get call hierarchy data for callers and/or callees."""
	app = _get_app_context(ctx)
	result = await navigation_call_hierarchy(
		app.pyright,
		file_path,
		line,
		character,
		direction,
		depth,
		max_items,
	)
	await ctx.debug(
		"call_hierarchy callers="
		f"{len(result.callers)} callees={len(result.callees)} depth={depth} direction={direction}"
	)
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def goto_definition(ctx: MCPContext, file_path: str, line: int, character: int) -> list[Location]:
	"""Navigate to symbol definitions for the provided source location."""
	app = _get_app_context(ctx)
	result = await navigation_goto_definition(app.pyright, app.jedi, file_path, line, character)
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
) -> list[SymbolOutlineItem]:
	"""Get hierarchical symbol outline for a file or the full workspace."""
	app = _get_app_context(ctx)
	result = await navigation_get_symbol_outline(app.pyright, app.config, file_path, kind_filter, name_pattern, limit)
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
) -> TypeHierarchyResult:
	"""Get type hierarchy data for supertypes/subtypes from a source position."""
	app = _get_app_context(ctx)
	result = await navigation_type_hierarchy(
		app.pyright,
		file_path,
		line,
		character,
		direction,
		depth,
		max_items,
	)
	await ctx.debug(
		"type_hierarchy supertypes="
		f"{len(result.supertypes)} subtypes={len(result.subtypes)} depth={depth} direction={direction}"
	)
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def selection_range(
	ctx: MCPContext,
	file_path: str,
	positions: list[Position],
) -> list[SelectionRangeResult]:
	"""Get nested selection ranges for one or more positions in a file."""
	app = _get_app_context(ctx)
	result = await navigation_selection_range(app.pyright, file_path, positions)
	await ctx.debug(f"selection_range count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def find_implementations(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
) -> list[Location]:
	"""Find implementation locations for the symbol at the source position."""
	app = _get_app_context(ctx)
	result = await navigation_find_implementations(app.pyright, file_path, line, character)
	await ctx.debug(f"find_implementations count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_declaration(ctx: MCPContext, file_path: str, line: int, character: int) -> list[Location]:
	"""Navigate to declaration sites for the symbol at the source location."""
	app = _get_app_context(ctx)
	result = await navigation_get_declaration(app.pyright, file_path, line, character)
	await ctx.debug(f"get_declaration count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_type_definition(ctx: MCPContext, file_path: str, line: int, character: int) -> list[Location]:
	"""Navigate to type definitions for the symbol at the source location."""
	app = _get_app_context(ctx)
	result = await navigation_get_type_definition(app.pyright, file_path, line, character)
	await ctx.debug(f"get_type_definition count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_folding_ranges(ctx: MCPContext, file_path: str) -> list[FoldingRange]:
	"""Return foldable regions to support chunked file analysis workflows."""
	app = _get_app_context(ctx)
	result = await navigation_get_folding_ranges(app.pyright, file_path)
	await ctx.debug(f"get_folding_ranges count={len(result)}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def rename_symbol(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	new_name: str,
	apply: bool = False,
) -> RefactorResult:
	"""Rename a symbol and optionally apply edits to disk."""
	app = _get_app_context(ctx)
	result = await refactoring_rename_symbol(
		app.pyright,
		app.rope,
		file_path,
		line,
		character,
		new_name,
		apply,
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
	"""Extract selected code into a new method."""
	app = _get_app_context(ctx)
	result = await refactoring_extract_method(
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
	"""Extract selected expression into a variable."""
	app = _get_app_context(ctx)
	result = await refactoring_extract_variable(
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
	await ctx.debug(f"extract_variable edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def inline_variable(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	apply: bool = False,
) -> RefactorResult:
	"""Inline variable usage at a source position."""
	app = _get_app_context(ctx)
	result = await refactoring_inline_variable(app.pyright, app.rope, file_path, line, character, apply)
	await ctx.debug(f"inline_variable edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def move_symbol(
	ctx: MCPContext,
	source_file: str,
	symbol_name: str,
	destination_file: str,
	apply: bool = False,
) -> RefactorResult:
	"""Move a symbol from one file to another."""
	app = _get_app_context(ctx)
	result = await refactoring_move_symbol(
		app.pyright,
		app.rope,
		source_file,
		symbol_name,
		destination_file,
		apply,
	)
	await ctx.debug(f"move_symbol edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def apply_code_action(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	action_title: str | None = None,
	apply: bool = False,
) -> RefactorResult:
	"""Apply or preview a Pyright code action at the provided location."""
	app = _get_app_context(ctx)
	result = await refactoring_apply_code_action(app.pyright, file_path, line, character, action_title, apply)
	await ctx.debug(f"apply_code_action edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def organize_imports(
	ctx: MCPContext,
	file_path: str,
	apply: bool = False,
) -> RefactorResult:
	"""Organize imports for a file and optionally apply the edits."""
	app = _get_app_context(ctx)
	result = await refactoring_organize_imports(app.pyright, file_path, apply)
	await ctx.debug(f"organize_imports edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def prepare_rename(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
) -> PrepareRenameResult | None:
	"""Run rename preflight checks and return editable range metadata when valid."""
	app = _get_app_context(ctx)
	result = await refactoring_prepare_rename(app.pyright, file_path, line, character)
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
	"""Introduce a parameter and optionally apply updates to call sites."""
	app = _get_app_context(ctx)
	result = await refactoring_introduce_parameter(
		app.pyright,
		app.rope,
		file_path,
		line,
		character,
		parameter_name,
		default_value,
		apply,
	)
	await ctx.debug(f"introduce_parameter edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def encapsulate_field(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	apply: bool = False,
) -> RefactorResult:
	"""Encapsulate a field using property accessors and optional apply mode."""
	app = _get_app_context(ctx)
	result = await refactoring_encapsulate_field(app.pyright, app.rope, file_path, line, character, apply)
	await ctx.debug(f"encapsulate_field edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def find_constructors(
	ctx: MCPContext,
	class_name: str,
	file_path: str | None = None,
	limit: int | None = None,
) -> list[ConstructorSite]:
	"""Find constructor call sites for a class."""
	app = _get_app_context(ctx)
	result = await search_find_constructors(app.pyright, app.config, class_name, file_path, limit)
	await ctx.debug(f"find_constructors class={class_name} count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def search_symbols(ctx: MCPContext, query: str, limit: int | None = None) -> list[SymbolInfo]:
	"""Search workspace symbols by name across semantic backends."""
	app = _get_app_context(ctx)
	result = await search_search_symbols(app.pyright, app.jedi, query, limit)
	await ctx.debug(f"search_symbols query={query} count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def structural_search(
	ctx: MCPContext,
	pattern: str,
	file_path: str | None = None,
	language: str = "python",
	limit: int | None = None,
) -> list[StructuralMatch]:
	"""Search code structurally using a pattern expression."""
	app = _get_app_context(ctx)
	result = await search_structural_search(app.config, pattern, file_path, language, limit)
	await ctx.debug(f"structural_search language={language} count={len(result)}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def dead_code_detection(
	ctx: MCPContext,
	file_path: str | None = None,
	exclude_patterns: list[str] | None = None,
) -> list[DeadCodeItem]:
	"""Detect dead code candidates in a file or workspace."""
	app = _get_app_context(ctx)
	result = await search_dead_code_detection(app.pyright, app.config, file_path, exclude_patterns)
	await ctx.debug(f"dead_code_detection count={len(result)}")
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
	"""Change function signature and update call sites."""
	app = _get_app_context(ctx)
	result = await refactoring_change_signature(app.pyright, app.rope, file_path, line, character, operations, apply)
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
	"""Apply structural replace pattern transformations."""
	app = _get_app_context(ctx)
	result = await refactoring_restructure(app.pyright, app.rope, pattern, goal, checks, imports, file_path, apply)
	await ctx.debug(f"restructure edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def use_function(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	apply: bool = False,
) -> RefactorResult:
	"""Replace duplicated code with calls to selected function."""
	app = _get_app_context(ctx)
	result = await refactoring_use_function(app.pyright, app.rope, file_path, line, character, apply)
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
	"""Introduce a factory function for selected class constructor."""
	app = _get_app_context(ctx)
	result = await refactoring_introduce_factory(
		app.pyright,
		app.rope,
		file_path,
		line,
		character,
		factory_name,
		global_factory,
		apply,
	)
	await ctx.debug(f"introduce_factory edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def module_to_package(ctx: MCPContext, file_path: str, apply: bool = False) -> RefactorResult:
	"""Convert a module file into a package directory structure."""
	app = _get_app_context(ctx)
	result = await refactoring_module_to_package(app.pyright, app.rope, file_path, apply)
	await ctx.debug(f"module_to_package edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def local_to_field(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	apply: bool = False,
) -> RefactorResult:
	"""Promote a local variable to instance field usage."""
	app = _get_app_context(ctx)
	result = await refactoring_local_to_field(app.pyright, app.rope, file_path, line, character, apply)
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
	"""Extract selected method into a new callable object class."""
	app = _get_app_context(ctx)
	result = await refactoring_method_object(app.pyright, app.rope, file_path, line, character, classname, apply)
	await ctx.debug(f"method_object edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def suggest_imports(
	ctx: MCPContext,
	symbol: str,
	file_path: str,
) -> list[ImportSuggestion]:
	"""Suggest import statements for an unresolved symbol."""
	app = _get_app_context(ctx)
	result = await search_suggest_imports(app.pyright, app.jedi, symbol, file_path)
	await ctx.debug(f"suggest_imports symbol={symbol} count={len(result)}")
	return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def smart_rename(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	new_name: str,
	apply: bool = False,
) -> RefactorResult:
	"""Perform a coordinated rename workflow across backends."""
	app = _get_app_context(ctx)
	result = await composite_smart_rename(
		app.pyright,
		app.rope,
		file_path,
		line,
		character,
		new_name,
		apply,
	)
	await ctx.debug(f"smart_rename edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def diff_preview(ctx: MCPContext, edits: list[TextEdit]) -> list[DiffPreview]:
	"""Build unified diff previews for pending text edits."""
	_ = _get_app_context(ctx)
	result = await composite_diff_preview(edits)
	await ctx.debug(f"diff_preview files={len(result)}")
	return result


def run_server(workspace_root: str) -> None:
	"""Start the FastMCP server using stdio transport."""
	global _workspace_root
	_workspace_root = Path(workspace_root).resolve()
	mcp.run()


