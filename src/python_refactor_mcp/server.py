"""MCP server shell and tool registration."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from python_refactor_mcp import __version__
from python_refactor_mcp.config import TOOL_PROFILE_ENV, ToolProfile, discover_max_workspaces, discover_tool_profile
from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import (
    BackendLiveness,
    CompletionItem,
    InlayHint,
    RefactorResult,
    SecurityScanResult,
    ServerStatus,
    SignatureOperation,
    SymbolOutlineResult,
    TestCoverageMap,
    UnusedImportScanResult,
)
from python_refactor_mcp.tool_registry import (
    DESTRUCTIVE_ANNOTATIONS,
    READ_ONLY_ANNOTATIONS,
    ToolRecord,
    register_tools,
    tool_names_for_profile,
)
from python_refactor_mcp.tool_runtime import MultiWorkspaceContext, get_current_backends, get_multi_context
from python_refactor_mcp.tools import analysis, metrics, navigation, refactoring
from python_refactor_mcp.tools.metrics.security import security_scan as _security_scan
from python_refactor_mcp.tools.metrics.test_map import get_test_coverage_map as _get_test_coverage_map
from python_refactor_mcp.tools.refactoring.security_autofix import security_autofix as _security_autofix
from python_refactor_mcp.tools.search.structural import structural_replace as _structural_replace
from python_refactor_mcp.util.shared import apply_limit
from python_refactor_mcp.workspace_registry import WorkspaceRegistry

_LOGGER = logging.getLogger(__name__)

# Default payload bounds for workspace-wide get_symbol_outline scans.
_WORKSPACE_OUTLINE_ROOT_LIMIT = 500
_WORKSPACE_OUTLINE_MAX_NODES = 250
_workspace_root: Path | None = None


# ── Server lifecycle ─────────────────────────────────────────────────────


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncGenerator[MultiWorkspaceContext]:
    """Create workspace registry and optionally pre-warm the CLI workspace."""
    _ = server
    max_ws = discover_max_workspaces()
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
        "- **Refactoring** (rename_symbol, extract_method, move_symbol, ...): Transform code safely with preview support.\n"
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

# ═══════════════════════════════════════════════════════════════════════════
#  Analysis tools
# ═══════════════════════════════════════════════════════════════════════════


async def get_completions(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    limit: int | None = None,
    fuzzy: bool = False,
) -> list[CompletionItem]:
    """Get code completion candidates at a cursor position. Use when suggesting what a user might type next — returns available symbols, methods, and keywords at the given location. Sorted by label. Set fuzzy=True for fuzzy matching (e.g., 'ooa' matches 'foobar'). Related: get_signature_help (for call-site parameter info). Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    if fuzzy:
        result = await app.jedi.get_completions(file_path, line, character, fuzzy=True)
        result, _ = apply_limit(result, limit)
    else:
        result = await analysis.get_completions(app.pyright, file_path, line, character, limit)
    _LOGGER.debug("get_completions count=%s fuzzy=%s", len(result), fuzzy)
    return result


async def get_inlay_hints(
    ctx: Context,
    file_path: str,
    start_line: int = 0,
    start_character: int = 0,
    end_line: int | None = None,
    end_character: int = 0,
) -> list[InlayHint]:
    """Get inlay hints (inline type annotations, parameter names) for a file range. Use to visualize inferred types and parameter labels that aren't written in the source. Defaults to the full file when end_line is omitted. Related: get_type_info, get_semantic_tokens. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    if end_line is None:
        try:
            line_count = len(Path(file_path).read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeError) as exc:
            raise BackendError(f"Cannot read file for line count: {exc}") from exc
        end_line = max(line_count, 0)
    result = await analysis.get_inlay_hints(
        app.pyright,
        file_path,
        start_line,
        start_character,
        end_line,
        end_character,
    )
    _LOGGER.debug("get_inlay_hints count=%s", len(result))
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  Navigation tools
# ═══════════════════════════════════════════════════════════════════════════


async def get_symbol_outline(
    ctx: Context,
    file_path: str | None = None,
    kind_filter: list[str] | None = None,
    name_pattern: str | None = None,
    limit: int | None = None,
    root_path: str | None = None,
    file_paths: list[str] | None = None,
    offset: int = 0,
    max_nodes: int | None = None,
) -> SymbolOutlineResult:
    """Get a hierarchical outline of classes, functions, and variables in a file or across the workspace. Use to understand code structure at a glance, find symbols by name pattern, or filter by kind (class, function, variable). Returns {items, total_count, offset, truncated, total_nodes, returned_nodes}. Supports pagination via offset/limit (limit counts root items). max_nodes caps roots plus descendants; a root crossing the budget keeps a depth-first prefix of its children. Workspace-wide scans (no file_path/file_paths) default to limit=500 roots and max_nodes=250; single-file and batch outlines are unbounded unless set. Check truncated before assuming completeness. Related: search_symbols (name-based search), get_folding_ranges."""
    app = get_current_backends()
    # Workspace-wide scans default to bounded output: a full-repo outline is
    # otherwise megabytes (500 roots once carried ~10k descendant nodes).
    effective_limit = limit
    effective_max_nodes = max_nodes
    if file_path is None and file_paths is None:
        if effective_limit is None:
            effective_limit = _WORKSPACE_OUTLINE_ROOT_LIMIT
        if effective_max_nodes is None:
            effective_max_nodes = _WORKSPACE_OUTLINE_MAX_NODES
    result = await navigation.get_symbol_outline(
        app.pyright,
        app.config,
        file_path,
        kind_filter,
        name_pattern,
        effective_limit,
        root_path,
        file_paths,
        offset,
        effective_max_nodes,
    )
    _LOGGER.debug(
        "get_symbol_outline roots=%s nodes=%s/%s truncated=%s",
        len(result.items),
        result.returned_nodes,
        result.total_nodes,
        result.truncated,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  Refactoring tools
# ═══════════════════════════════════════════════════════════════════════════


async def argument_normalizer(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Normalize call-site arguments to match the function definition's parameter order. Use to clean up keyword arguments that are passed in a different order than the signature defines. Convenience wrapper over change_signature with op='normalize'. Defaults to preview mode. Related: change_signature, argument_default_inliner. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    ops = [SignatureOperation(op="normalize")]
    result = await refactoring.change_signature(app.pyright, app.rope, file_path, line, character, ops, apply)
    _LOGGER.debug("argument_normalizer edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def argument_default_inliner(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    index: Annotated[int, Field(ge=0)],
    apply: bool = False,
) -> RefactorResult:
    """Inline a parameter's default value into all call sites that omit it, then remove the default from the signature. Use to push defaults to callers before removing the parameter. The index is the 0-based parameter position (``self`` counts for methods); it must name a parameter that has a default, and no earlier parameter may keep a default. Convenience wrapper over change_signature with op='inline_default'. Defaults to preview mode. Related: change_signature, argument_normalizer. Positions are 0-based (line and character offsets, LSP convention)."""
    app = get_current_backends()
    ops = [SignatureOperation(op="inline_default", index=index)]
    result = await refactoring.change_signature(app.pyright, app.rope, file_path, line, character, ops, apply)
    _LOGGER.debug("argument_default_inliner edits=%s applied=%s", len(result.edits), result.applied)
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  Metrics & Architecture tools
# ═══════════════════════════════════════════════════════════════════════════


async def find_unused_imports(
    ctx: Context,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
) -> UnusedImportScanResult:
    """Find unused imports using Pyright diagnostics merged with an AST fallback. Items and partial file/backend scan_failures are returned separately. Use to clean up import sections before committing. Provide file_path for a single file, or file_paths for batch mode. Related: organize_imports, expand_star_imports."""
    app = get_current_backends()
    if file_path is None and not file_paths:
        raise ValueError("Either file_path or file_paths must be provided.")
    effective_path = file_path if file_path is not None else file_paths[0]  # type: ignore[index]
    result = await metrics.find_unused_imports(app.pyright, effective_path, file_paths)
    log = _LOGGER.warning if result.scan_failures else _LOGGER.debug
    log("find_unused_imports count=%s scan_failures=%s", len(result.items), len(result.scan_failures))
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  P4 Feature Tools
# ═══════════════════════════════════════════════════════════════════════════


async def get_test_coverage_map(
    ctx: Context,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
) -> TestCoverageMap:
    """Map source symbols to test references. Shows which functions/classes have test coverage without treating failed reference lookups as uncovered; partial failures are returned in scan_failures. Related: find_references, dead_code_detection."""
    app = get_current_backends()
    result = await _get_test_coverage_map(app.pyright, file_path, file_paths)
    log = _LOGGER.warning if result.scan_failures else _LOGGER.debug
    log(
        "get_test_coverage_map total=%s covered=%s scan_failures=%s",
        result.total_symbols,
        result.covered_count,
        len(result.scan_failures),
    )
    return result


async def security_scan(
    ctx: Context,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
) -> SecurityScanResult:
    """AST-based security scan for common Python vulnerabilities (eval, exec, shell injection, pickle, etc.). Unreadable or unparseable files are returned in scan_failures rather than treated as clean. Related: get_diagnostics, dead_code_detection."""
    _ = get_current_backends()
    result = await _security_scan(file_path, file_paths)
    log = _LOGGER.warning if result.scan_failures else _LOGGER.debug
    log(
        "security_scan files=%s findings=%s scan_failures=%s",
        result.files_scanned,
        result.total_findings,
        len(result.scan_failures),
    )
    return result


async def security_autofix(
    ctx: Context,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Rewrite unsafe yaml.load() calls (SEC022) to yaml.safe_load(). Targets the literal yaml.load attribute call; calls that already pass an explicit Loader= are skipped (reported in the description). Defaults to preview mode (apply=False). Behavior-changing: safe_load rejects arbitrary tags/object construction that load permits. Related: security_scan."""
    app = get_current_backends()
    result = await _security_autofix(app.pyright, file_path, file_paths, apply)
    _LOGGER.debug("security_autofix edits=%s applied=%s", len(result.edits), result.applied)
    return result


async def structural_replace(
    ctx: Context,
    pattern: str,
    replacement: str,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Find structural matches with a LibCST matcher pattern and rewrite them. The pattern uses the same matcher DSL as structural_search (e.g. m.Call(func=m.Attribute(value=m.Name('logger'), attr=m.Name('warn')), args=[m.SaveMatchedNode(m.ZeroOrMore(m.Arg()), 'a')])); capture sub-nodes with m.SaveMatchedNode(matcher, 'name') and reference them in the replacement template as $name (e.g. 'logger.warning($a)'). Expression-position matches only. Requires file_path or file_paths; defaults to preview mode (apply=False). Related: structural_search, restructure."""
    app = get_current_backends()
    result = await _structural_replace(app.pyright, pattern, replacement, file_path, file_paths, apply)
    _LOGGER.debug("structural_replace edits=%s applied=%s", len(result.edits), result.applied)
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  Utility tools
# ═══════════════════════════════════════════════════════════════════════════


def _build_server_status(multi_ctx: MultiWorkspaceContext) -> ServerStatus:
    """Assemble a :class:`ServerStatus` from the lifespan registry state.

    Pure and synchronous (no analysis round-trips) so it is directly testable
    without the MCP context/boundary harness. ``degraded`` is True when no
    loaded workspace has a live Pyright subprocess.
    """
    registry = multi_ctx.registry
    workspaces = [
        BackendLiveness(
            workspace_root=str(wb.config.workspace_root),
            initialized=wb.is_initialized,
            pyright_running=wb.pyright.is_running,
            jedi_ready=wb.jedi.is_ready,
            rope_ready=wb.rope.is_ready,
            python_executable=str(wb.config.python_executable),
            pyright_executable=wb.config.pyright_executable,
        )
        for wb in registry.active_backends()
    ]
    return ServerStatus(
        version=__version__,
        cli_workspace_root=str(multi_ctx.cli_workspace_root) if multi_ctx.cli_workspace_root else None,
        known_roots=[str(root) for root in registry.get_known_roots()],
        active_workspaces=workspaces,
        degraded=not any(w.pyright_running for w in workspaces),
    )


async def server_status(ctx: Context) -> ServerStatus:
    """Report read-only server health: version, known workspace roots, and per-workspace backend liveness (Pyright subprocess up, Jedi/rope ready). Use to tell whether results came from a healthy Pyright or a degraded Jedi fallback. Works even when no workspace is loaded. Probes are cheap and non-blocking. Related: list_environments, restart_server."""
    status = _build_server_status(get_multi_context(ctx))
    _LOGGER.debug("server_status workspaces=%s degraded=%s", len(status.active_workspaces), status.degraded)
    return status


EXPLICIT_TOOL_RECORDS: tuple[ToolRecord, ...] = (
    ToolRecord(get_completions, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_inlay_hints, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_symbol_outline, READ_ONLY_ANNOTATIONS),
    ToolRecord(argument_normalizer, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(argument_default_inliner, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(find_unused_imports, READ_ONLY_ANNOTATIONS),
    ToolRecord(get_test_coverage_map, READ_ONLY_ANNOTATIONS),
    ToolRecord(security_scan, READ_ONLY_ANNOTATIONS),
    ToolRecord(security_autofix, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(structural_replace, DESTRUCTIVE_ANNOTATIONS),
    ToolRecord(server_status, READ_ONLY_ANNOTATIONS),
)

mcp = MCPServer(
    "Python Refactor",
    instructions=build_server_instructions(
        _ACTIVE_TOOL_PROFILE,
        tool_names_for_profile(_ACTIVE_TOOL_PROFILE, extra_records=EXPLICIT_TOOL_RECORDS),
    ),
    lifespan=app_lifespan,
    version=__version__,
)

register_tools(
    mcp,
    _ACTIVE_TOOL_PROFILE,
    extra_records=EXPLICIT_TOOL_RECORDS,
)


# ═══════════════════════════════════════════════════════════════════════════
#  Server entrypoint
# ═══════════════════════════════════════════════════════════════════════════


def run_server(workspace_root: str | None = None) -> None:
    """Start the MCP server using stdio transport.

    If *workspace_root* is provided, backends for that workspace are
    eagerly initialized at startup.  If omitted, the server starts cold
    and discovers workspaces dynamically from path parameters on the first
    path-bearing tool call.
    """
    global _workspace_root  # noqa: PLW0603
    _workspace_root = Path(workspace_root).resolve() if workspace_root else None
    mcp.run()
