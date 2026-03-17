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
) -> str:
	"""Find symbol references for the provided source location."""
	_ = _get_app_context(ctx)
	return await analysis_find_references(file_path, line, character, include_declaration)


@mcp.tool()
async def get_type_info(ctx: MCPContext, file_path: str, line: int, character: int) -> str:
	"""Get type information for the provided source location."""
	_ = _get_app_context(ctx)
	return await analysis_get_type_info(file_path, line, character)


@mcp.tool()
async def get_diagnostics(
	ctx: MCPContext,
	file_path: str | None = None,
	severity_filter: str | None = None,
) -> str:
	"""Get diagnostics for a file or for the full workspace."""
	_ = _get_app_context(ctx)
	return await analysis_get_diagnostics(file_path, severity_filter)


@mcp.tool()
async def call_hierarchy(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	direction: str = "both",
	depth: int = 1,
) -> str:
	"""Get call hierarchy data for callers and/or callees."""
	_ = _get_app_context(ctx)
	return await navigation_call_hierarchy(file_path, line, character, direction, depth)


@mcp.tool()
async def goto_definition(ctx: MCPContext, file_path: str, line: int, character: int) -> str:
	"""Navigate to symbol definitions for the provided source location."""
	_ = _get_app_context(ctx)
	return await navigation_goto_definition(file_path, line, character)


@mcp.tool()
async def rename_symbol(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	new_name: str,
	apply: bool = False,
) -> str:
	"""Rename a symbol and optionally apply edits to disk."""
	_ = _get_app_context(ctx)
	return await refactoring_rename_symbol(file_path, line, character, new_name, apply)


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
) -> str:
	"""Extract selected code into a new method."""
	_ = _get_app_context(ctx)
	return await refactoring_extract_method(
		file_path,
		start_line,
		start_character,
		end_line,
		end_character,
		method_name,
		apply,
	)


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
) -> str:
	"""Extract selected expression into a variable."""
	_ = _get_app_context(ctx)
	return await refactoring_extract_variable(
		file_path,
		start_line,
		start_character,
		end_line,
		end_character,
		variable_name,
		apply,
	)


@mcp.tool()
async def inline_variable(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	apply: bool = False,
) -> str:
	"""Inline variable usage at a source position."""
	_ = _get_app_context(ctx)
	return await refactoring_inline_variable(file_path, line, character, apply)


@mcp.tool()
async def move_symbol(
	ctx: MCPContext,
	source_file: str,
	symbol_name: str,
	destination_file: str,
	apply: bool = False,
) -> str:
	"""Move a symbol from one file to another."""
	_ = _get_app_context(ctx)
	return await refactoring_move_symbol(source_file, symbol_name, destination_file, apply)


@mcp.tool()
async def find_constructors(ctx: MCPContext, class_name: str, file_path: str | None = None) -> str:
	"""Find constructor call sites for a class."""
	_ = _get_app_context(ctx)
	return await search_find_constructors(class_name, file_path)


@mcp.tool()
async def structural_search(
	ctx: MCPContext,
	pattern: str,
	file_path: str | None = None,
	language: str = "python",
) -> str:
	"""Search code structurally using a pattern expression."""
	_ = _get_app_context(ctx)
	return await search_structural_search(pattern, file_path, language)


@mcp.tool()
async def dead_code_detection(ctx: MCPContext, file_path: str | None = None) -> str:
	"""Detect dead code candidates in a file or workspace."""
	_ = _get_app_context(ctx)
	return await search_dead_code_detection(file_path)


@mcp.tool()
async def suggest_imports(ctx: MCPContext, symbol: str, file_path: str) -> str:
	"""Suggest import statements for an unresolved symbol."""
	_ = _get_app_context(ctx)
	return await search_suggest_imports(symbol, file_path)


@mcp.tool()
async def smart_rename(
	ctx: MCPContext,
	file_path: str,
	line: int,
	character: int,
	new_name: str,
	apply: bool = False,
) -> str:
	"""Perform a coordinated rename workflow across backends."""
	_ = _get_app_context(ctx)
	return await composite_smart_rename(file_path, line, character, new_name, apply)


def run_server(workspace_root: str) -> None:
	"""Start the FastMCP server using stdio transport."""
	global _workspace_root
	_workspace_root = Path(workspace_root).resolve()
	mcp.run()
