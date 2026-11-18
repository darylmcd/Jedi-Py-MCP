"""MCP server shell: lifecycle, instructions and entrypoint (tools live in tool_registry)."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from python_refactor_mcp import __version__
from python_refactor_mcp.config import TOOL_PROFILE_ENV, ToolProfile, discover_max_workspaces, discover_tool_profile
from python_refactor_mcp.tool_registry import build_tools, tool_names_for_profile
from python_refactor_mcp.tool_runtime import MultiWorkspaceContext
from python_refactor_mcp.util.shared import require_local_path
from python_refactor_mcp.workspace_registry import WorkspaceRegistry

# ── Server lifecycle ─────────────────────────────────────────────────────


def workspace_lifespan(
    workspace_root: Path | None,
) -> Callable[[MCPServer], AbstractAsyncContextManager[MultiWorkspaceContext]]:
    """Return a lifespan that owns one workspace registry and pre-warms *workspace_root*.

    The root travels in the closure, so servers built in one process share no state.
    Every startup step runs inside the ``try`` whose ``finally`` owns teardown.
    """

    @asynccontextmanager
    async def lifespan(server: MCPServer) -> AsyncGenerator[MultiWorkspaceContext]:
        _ = server
        registry = WorkspaceRegistry(max_workspaces=discover_max_workspaces())
        try:
            if workspace_root is not None:
                await registry.set_roots([workspace_root])
                # Eagerly start the CLI workspace's backends without selecting it: a path-less
                # call must still name its workspace (root_path) or follow a path-bearing call.
                await registry.prewarm(workspace_root)
            yield MultiWorkspaceContext(registry=registry, cli_workspace_root=workspace_root)
        finally:
            await registry.shutdown_all()

    return lifespan


_ACTIVE_TOOL_PROFILE = discover_tool_profile()

# Instruction lines as (text, tool names the text cites). A line is emitted only
# when the active profile advertises every tool it names, so the instructions
# never point a client at a hidden tool.
_InstructionLine = tuple[str, tuple[str, ...]]

_REFACTORING_EXAMPLES = ("rename_symbol", "extract_method", "move_symbol")

_CATEGORY_LINES: tuple[_InstructionLine, ...] = (
    (
        "- **Analysis** (find_references, get_type_info, get_diagnostics, ...): Inspect code without modifying it.",
        ("find_references", "get_type_info", "get_diagnostics"),
    ),
    (
        "- **Navigation** (goto_definition, get_symbol_outline, selection_range, ...): Navigate code structure.",
        ("goto_definition", "get_symbol_outline", "selection_range"),
    ),
    (
        "- **Refactoring** (rename_symbol, extract_method, move_symbol, ...): "
        "Transform code safely with preview support.\n"
        "  Refactoring tools that accept apply default to preview (apply=False); "
        "tools without an apply parameter act immediately.",
        _REFACTORING_EXAMPLES,
    ),
    (
        "- **Search** (search_symbols, dead_code_detection, structural_search, ...): Find patterns and issues.",
        ("search_symbols", "dead_code_detection", "structural_search"),
    ),
)

_WORKFLOW_TIPS: tuple[_InstructionLine, ...] = (
    (
        "- Use find_references before rename_symbol to understand impact scope.",
        ("find_references", "rename_symbol"),
    ),
    (
        "- Use prepare_rename before rename_symbol to verify the symbol is renameable.",
        ("prepare_rename", "rename_symbol"),
    ),
    (
        "- Use get_diagnostics after applying changes to check for introduced errors.",
        ("get_diagnostics",),
    ),
    (
        "- Use diff_preview to visualize pending TextEdit lists before applying them.",
        ("diff_preview",),
    ),
    (
        "- Use get_type_info for type inspection; it combines Pyright and Jedi results.",
        ("get_type_info",),
    ),
)


def build_server_instructions(profile: ToolProfile, advertised: frozenset[str]) -> str:
    """Render server instructions that cite only tools in *advertised*.

    *profile* names the active surface; the analysis profile additionally notes
    that refactoring tools require the ``refactoring`` profile.
    """

    def _emitted(lines: tuple[_InstructionLine, ...]) -> list[str]:
        return [text for text, required in lines if all(name in advertised for name in required)]

    categories = _emitted(_CATEGORY_LINES)
    if profile == "analysis":
        categories.append(
            f'- Refactoring tools are not advertised in this profile; set {TOOL_PROFILE_ENV}="refactoring" to use them.'
        )
    sections = [
        "Python Refactor MCP provides semantic code analysis and automated refactoring for Python projects.",
        f"Active tool profile: {profile}. Configure {TOOL_PROFILE_ENV} as\n"
        '"analysis" or "refactoring" before startup to select the advertised surface.',
        "Tool categories:\n" + "\n".join(categories),
        "Workflow tips:\n" + "\n".join(_emitted(_WORKFLOW_TIPS)),
    ]
    return "\n\n".join(sections) + "\n"


def build_server(workspace_root: Path | None = None) -> MCPServer:
    """Build one MCP server whose lifespan pre-warms *workspace_root* (``None`` starts cold)."""
    return MCPServer(
        "Python Refactor",
        instructions=build_server_instructions(
            _ACTIVE_TOOL_PROFILE,
            tool_names_for_profile(_ACTIVE_TOOL_PROFILE),
        ),
        lifespan=workspace_lifespan(workspace_root),
        version=__version__,
        tools=build_tools(_ACTIVE_TOOL_PROFILE),
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Server entrypoint
# ═══════════════════════════════════════════════════════════════════════════


def run_server(workspace_root: str | None = None) -> None:
    """Start the MCP server using stdio transport.

    If *workspace_root* is provided (single-project registrations only), backends
    for that workspace are eagerly initialized at startup but the workspace is not
    selected: a path-less call fails until a path-bearing call or ``root_path``
    selects it.  If omitted, the server starts cold and discovers workspaces
    dynamically from path parameters on path-bearing tool calls. A UNC or
    device-namespace *workspace_root* raises ``ToolInputError`` before any
    filesystem access.
    """
    if workspace_root:
        require_local_path(workspace_root, "workspace_root")
    build_server(Path(workspace_root).resolve() if workspace_root else None).run()
