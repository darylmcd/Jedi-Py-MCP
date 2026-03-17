"""FastMCP server shell and tool registration for Stage 1."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP

from python_refactor_mcp.backends.jedi_backend import JediBackend
from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient
from python_refactor_mcp.backends.rope_backend import RopeBackend
from python_refactor_mcp.config import ServerConfig, discover_config
from python_refactor_mcp.models import (
	CallHierarchyResult,
	ConstructorSite,
	DeadCodeItem,
	Diagnostic,
	ImportSuggestion,
	Location,
	RefactorResult,
	ReferenceResult,
	StructuralMatch,
	TypeInfo,
)
from python_refactor_mcp.tools.analysis import (
	find_references as analysis_find_references,
)
from python_refactor_mcp.tools.analysis import (
	get_diagnostics as analysis_get_diagnostics,
)
from python_refactor_mcp.tools.analysis import get_type_info as analysis_get_type_info
from python_refactor_mcp.tools.composite import smart_rename as composite_smart_rename
from python_refactor_mcp.tools.navigation import call_hierarchy as navigation_call_hierarchy
from python_refactor_mcp.tools.navigation import goto_definition as navigation_goto_definition
from python_refactor_mcp.tools.refactoring import extract_method as refactoring_extract_method
from python_refactor_mcp.tools.refactoring import extract_variable as refactoring_extract_variable
from python_refactor_mcp.tools.refactoring import inline_variable as refactoring_inline_variable
from python_refactor_mcp.tools.refactoring import move_symbol as refactoring_move_symbol
from python_refactor_mcp.tools.refactoring import rename_symbol as refactoring_rename_symbol
from python_refactor_mcp.tools.search import dead_code_detection as search_dead_code_detection
from python_refactor_mcp.tools.search import find_constructors as search_find_constructors
from python_refactor_mcp.tools.search import structural_search as search_structural_search
from python_refactor_mcp.tools.search import suggest_imports as search_suggest_imports


@dataclass(slots=True)
class AppContext:
	"""Application lifespan context shared by all MCP tools."""

	pyright: PyrightLSPClient
	jedi: JediBackend
	rope: RopeBackend
	config: ServerConfig


_workspace_root: Path | None = None
MCPContext = Context  # type: ignore[type-arg]


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


@mcp.tool()
async def find_references(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	include_declaration: bool = True,
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
	)
	await ctx.debug(f"find_references source={result.source} count={result.total_count}")
	return result


@mcp.tool()
async def get_type_info(ctx: MCPContext, file_path: str, line: int, character: int) -> TypeInfo:
	"""Get type information for the provided source location."""
	app = _get_app_context(ctx)
	result = await analysis_get_type_info(app.pyright, app.jedi, file_path, line, character)
	await ctx.debug(f"get_type_info source={result.source} type={result.type_string}")
	return result


@mcp.tool()
async def get_diagnostics(
	ctx: MCPContext,
	file_path: str | None = None,
	severity_filter: str | None = None,
) -> list[Diagnostic]:
	"""Get diagnostics for a file or for the full workspace."""
	app = _get_app_context(ctx)
	result = await analysis_get_diagnostics(app.pyright, file_path, severity_filter)
	await ctx.debug(f"get_diagnostics count={len(result)} severity_filter={severity_filter}")
	return result


@mcp.tool()
async def call_hierarchy(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	direction: str = "both",
	depth: int = 1,
) -> CallHierarchyResult:
	"""Get call hierarchy data for callers and/or callees."""
	app = _get_app_context(ctx)
	result = await navigation_call_hierarchy(app.pyright, file_path, line, character, direction, depth)
	await ctx.debug(
		"call_hierarchy callers="
		f"{len(result.callers)} callees={len(result.callees)} depth={depth} direction={direction}"
	)
	return result


@mcp.tool()
async def goto_definition(ctx: MCPContext, file_path: str, line: int, character: int) -> list[Location]:
	"""Navigate to symbol definitions for the provided source location."""
	app = _get_app_context(ctx)
	result = await navigation_goto_definition(app.pyright, app.jedi, file_path, line, character)
	await ctx.debug(f"goto_definition count={len(result)}")
	return result


@mcp.tool()
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


@mcp.tool()
async def extract_method(
	ctx: MCPContext,
	file_path: str,
	start_line: int,
	start_character: int,
	end_line: int,
	end_character: int,
	method_name: str,
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
		apply,
	)
	await ctx.debug(f"extract_method edits={len(result.edits)} applied={result.applied}")
	return result


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
async def find_constructors(
	ctx: MCPContext,
	class_name: str,
	file_path: str | None = None,
) -> list[ConstructorSite]:
	"""Find constructor call sites for a class."""
	app = _get_app_context(ctx)
	result = await search_find_constructors(app.pyright, app.config, class_name, file_path)
	await ctx.debug(f"find_constructors class={class_name} count={len(result)}")
	return result


@mcp.tool()
async def structural_search(
	ctx: MCPContext,
	pattern: str,
	file_path: str | None = None,
	language: str = "python",
) -> list[StructuralMatch]:
	"""Search code structurally using a pattern expression."""
	app = _get_app_context(ctx)
	result = await search_structural_search(app.config, pattern, file_path, language)
	await ctx.debug(f"structural_search language={language} count={len(result)}")
	return result


@mcp.tool()
async def dead_code_detection(
	ctx: MCPContext,
	file_path: str | None = None,
) -> list[DeadCodeItem]:
	"""Detect dead code candidates in a file or workspace."""
	app = _get_app_context(ctx)
	result = await search_dead_code_detection(app.pyright, app.config, file_path)
	await ctx.debug(f"dead_code_detection count={len(result)}")
	return result


@mcp.tool()
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


@mcp.tool()
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


def run_server(workspace_root: str) -> None:
	"""Start the FastMCP server using stdio transport."""
	global _workspace_root
	_workspace_root = Path(workspace_root).resolve()
	mcp.run()
