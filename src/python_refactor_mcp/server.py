"""MCP server shell and tool registration."""

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

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from python_refactor_mcp import __version__
from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import (
    BackendLiveness,
    CompletionItem,
    InlayHint,
    RefactorResult,
    SecurityScanResult,
    ServerStatus,
    SignatureOperation,
    SymbolOutlineItem,
    TestCoverageMap,
    UnusedImport,
)
from python_refactor_mcp.tools import analysis, metrics, navigation, refactoring
from python_refactor_mcp.tools.metrics.security import security_scan as _security_scan
from python_refactor_mcp.tools.metrics.test_map import get_test_coverage_map as _get_test_coverage_map
from python_refactor_mcp.tools.refactoring.security_autofix import security_autofix as _security_autofix
from python_refactor_mcp.tools.search.structural import structural_replace as _structural_replace
from python_refactor_mcp.util.shared import apply_limit, validate_identifier, validate_workspace_path
from python_refactor_mcp.workspace_registry import WorkspaceBackends, WorkspaceRegistry

# Tool annotation constants (``_READONLY`` / ``_DESTRUCTIVE`` / ``_ADDITIVE``)
# live in ``tool_registry`` and are imported near the ``register_tools`` call
# below (see that comment for the import-ordering rationale).

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
    "new_name",
    "method_name",
    "variable_name",
    "parameter_name",
    "factory_name",
    "classname",
)


def _transaction_step_args(kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    """Return mutable argument objects from well-shaped transaction steps."""
    steps = kwargs.get("steps")
    if not isinstance(steps, list):
        return []

    step_args: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        args = step.get("args")
        if isinstance(args, dict):
            step_args.append(args)
    return step_args


def _transaction_step_paths(kwargs: dict[str, Any]) -> list[str]:
    """Extract nested ``refactor_transaction`` file paths in request order."""
    return [file_path for args in _transaction_step_args(kwargs) if isinstance(file_path := args.get("file_path"), str)]


# ── Multi-workspace context ──────────────────────────────────────────────

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class MultiWorkspaceContext:
    """Lifespan context holding the workspace registry."""

    registry: WorkspaceRegistry
    cli_workspace_root: Path | None


_workspace_root: Path | None = None

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
            "No workspace backends available. Ensure the tool call was dispatched through _tool_error_boundary."
        )


def _get_multi_context(ctx: Context) -> MultiWorkspaceContext:
    """Extract MultiWorkspaceContext from the MCP lifespan context."""
    request_context = getattr(ctx, "request_context", None)
    if request_context is None:
        raise RuntimeError("MCP context is missing request_context.")

    lifespan_context = getattr(request_context, "lifespan_context", None)
    if not isinstance(lifespan_context, MultiWorkspaceContext):
        raise RuntimeError("MCP context is missing a valid MultiWorkspaceContext lifespan payload.")

    return lifespan_context


async def _resolve_backends(ctx: Context | None, kwargs: dict[str, Any]) -> WorkspaceBackends | None:
    """Resolve the WorkspaceBackends for a tool call from its context and kwargs.

    Performs the multi-workspace context lookup, primary-path extraction from
    path parameters, and the registry lookup (with the most-recent / CLI
    ``__fallback__`` paths for tools that take no file path). Returns ``None``
    when no workspace can be resolved (e.g. no context, or no
    MultiWorkspaceContext lifespan payload).
    """
    multi_ctx: MultiWorkspaceContext | None = None
    if ctx is not None:
        with contextlib.suppress(RuntimeError):
            multi_ctx = _get_multi_context(ctx)

    if multi_ctx is None:
        return None

    assert ctx is not None
    registry = multi_ctx.registry

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
    if primary_path is None:
        nested_paths = _transaction_step_paths(kwargs)
        if nested_paths:
            primary_path = nested_paths[0]

    # Resolve workspace backends.
    if primary_path is not None:
        return await registry.get_backends(primary_path)

    # Fallback for tools without file_path params.
    backends = registry.get_most_recent()
    if backends is None and multi_ctx.cli_workspace_root is not None:
        backends = await registry.get_backends(
            str(multi_ctx.cli_workspace_root / "__fallback__"),
        )
    return backends


def _validate_params(kwargs: dict[str, Any], workspace_root: Path) -> None:
    """Validate and normalize path + identifier parameters in place.

    Resolves path parameters against *workspace_root* (rejecting paths outside
    the boundary) and verifies identifier parameters are legal Python
    identifiers. Mutates *kwargs* with the resolved path strings.
    """
    for param_name in _PATH_PARAMS:
        value = kwargs.get(param_name)
        if isinstance(value, str):
            kwargs[param_name] = validate_workspace_path(value, workspace_root)

    for param_name in _LIST_PATH_PARAMS:
        values = kwargs.get(param_name)
        if isinstance(values, list):
            kwargs[param_name] = [validate_workspace_path(v, workspace_root) for v in values if isinstance(v, str)]

    for args in _transaction_step_args(kwargs):
        file_path = args.get("file_path")
        if isinstance(file_path, str):
            args["file_path"] = validate_workspace_path(file_path, workspace_root)

    for param_name in _IDENTIFIER_PARAMS:
        value = kwargs.get(param_name)
        if isinstance(value, str):
            validate_identifier(value, param_name)


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
        backends = await _resolve_backends(ctx, kwargs)

        # Set the ContextVar for the tool function.
        token = _current_backends.set(backends) if backends is not None else None
        try:
            # Identifier validation runs unconditionally; path validation
            # needs a resolved workspace to anchor the boundary check.
            if backends is not None:
                _validate_params(kwargs, backends.config.workspace_root)
            else:
                for param_name in _IDENTIFIER_PARAMS:
                    value = kwargs.get(param_name)
                    if isinstance(value, str):
                        validate_identifier(value, param_name)

            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            except BackendError as exc:
                # Backend failures are anticipated tool failures. ToolError keeps
                # the MCP SDK from classifying them as crashes, while the stable
                # prefix preserves backend provenance in the text-only error result.
                raise ToolError(f"[{exc.code}] {exc}") from exc
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                _LOGGER.debug("%s completed in %.1fms", func.__name__, elapsed_ms)
        finally:
            if token is not None:
                _current_backends.reset(token)

    return _wrapped


# ── Server lifecycle ─────────────────────────────────────────────────────


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncGenerator[MultiWorkspaceContext]:
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

mcp = MCPServer(
    "Python Refactor",
    instructions=_SERVER_INSTRUCTIONS,
    lifespan=app_lifespan,
    version=__version__,
)

# Register the 86 pure-delegation tools and pull in the shared annotation
# constants used by the eleven explicit wrappers below. Placed here (not at the
# top) so it runs after this module's ``_get_current_backends`` /
# ``_tool_error_boundary`` are defined: ``tool_registry`` imports those names
# back from this module — a deliberate, well-ordered import cycle.
from python_refactor_mcp.tool_registry import (  # noqa: E402
    _DESTRUCTIVE,  # pyright: ignore[reportPrivateUsage]
    _READONLY,  # pyright: ignore[reportPrivateUsage]
    register_tools,
)

register_tools(mcp)


# ═══════════════════════════════════════════════════════════════════════════
#  Analysis tools
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_completions(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    limit: int | None = None,
    fuzzy: bool = False,
) -> list[CompletionItem]:
    """Get code completion candidates at a cursor position. Use when suggesting what a user might type next — returns available symbols, methods, and keywords at the given location. Sorted by label. Set fuzzy=True for fuzzy matching (e.g., 'ooa' matches 'foobar'). Related: get_signature_help (for call-site parameter info). Positions are 0-based (line and character offsets, LSP convention)."""
    app = _get_current_backends()
    if fuzzy:
        result = await app.jedi.get_completions(file_path, line, character, fuzzy=True)
        result, _ = apply_limit(result, limit)
    else:
        result = await analysis.get_completions(app.pyright, file_path, line, character, limit)
    _LOGGER.debug("get_completions count=%s fuzzy=%s", len(result), fuzzy)
    return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_inlay_hints(
    ctx: Context,
    file_path: str,
    start_line: int = 0,
    start_character: int = 0,
    end_line: int | None = None,
    end_character: int = 0,
) -> list[InlayHint]:
    """Get inlay hints (inline type annotations, parameter names) for a file range. Use to visualize inferred types and parameter labels that aren't written in the source. Defaults to the full file when end_line is omitted. Related: get_type_info, get_semantic_tokens. Positions are 0-based (line and character offsets, LSP convention)."""
    app = _get_current_backends()
    if end_line is None:
        try:
            line_count = len(Path(file_path).read_text(encoding="utf-8").splitlines())
        except (FileNotFoundError, OSError) as exc:
            raise ValueError(f"Cannot read file for line count: {exc}") from exc
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


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_symbol_outline(
    ctx: Context,
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
        app.pyright,
        app.config,
        file_path,
        kind_filter,
        name_pattern,
        effective_limit,
        root_path,
        file_paths,
        offset,
    )
    _LOGGER.debug("get_symbol_outline count=%s", len(result))
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  Refactoring tools
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def argument_normalizer(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Normalize call-site arguments to match the function definition's parameter order. Use to clean up keyword arguments that are passed in a different order than the signature defines. Convenience wrapper over change_signature with op='normalize'. Defaults to preview mode. Related: change_signature, argument_default_inliner. Positions are 0-based (line and character offsets, LSP convention)."""
    app = _get_current_backends()
    ops = [SignatureOperation(op="normalize")]
    result = await refactoring.change_signature(app.pyright, app.rope, file_path, line, character, ops, apply)
    _LOGGER.debug("argument_normalizer edits=%s applied=%s", len(result.edits), result.applied)
    return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def argument_default_inliner(
    ctx: Context,
    file_path: str,
    line: int,
    character: int,
    index: int,
    apply: bool = False,
) -> RefactorResult:
    """Inline a parameter's default value into all call sites that omit it, then remove the default from the signature. Use to push defaults to callers before removing the parameter. The index is the 0-based parameter position. Convenience wrapper over change_signature with op='inline_default'. Defaults to preview mode. Related: change_signature, argument_normalizer. Positions are 0-based (line and character offsets, LSP convention)."""
    app = _get_current_backends()
    ops = [SignatureOperation(op="inline_default", index=index)]
    result = await refactoring.change_signature(app.pyright, app.rope, file_path, line, character, ops, apply)
    _LOGGER.debug("argument_default_inliner edits=%s applied=%s", len(result.edits), result.applied)
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  Metrics & Architecture tools
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def find_unused_imports(
    ctx: Context,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
) -> list[UnusedImport]:
    """Find unused imports using Pyright reportUnusedImport diagnostics with AST fallback. Use to clean up import sections before committing. Provide file_path for a single file, or file_paths for batch mode. Related: organize_imports, expand_star_imports."""
    app = _get_current_backends()
    if file_path is None and not file_paths:
        raise ValueError("Either file_path or file_paths must be provided.")
    effective_path = file_path if file_path is not None else file_paths[0]  # type: ignore[index]
    result = await metrics.find_unused_imports(app.pyright, effective_path, file_paths)
    _LOGGER.debug("find_unused_imports count=%s", len(result))
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  P4 Feature Tools
# ═══════════════════════════════════════════════════════════════════════════


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def get_test_coverage_map(
    ctx: Context,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
) -> TestCoverageMap:
    """Map source symbols to test references. Shows which functions/classes have test coverage. Related: find_references, dead_code_detection."""
    app = _get_current_backends()
    result = await _get_test_coverage_map(app.pyright, file_path, file_paths)
    _LOGGER.debug("get_test_coverage_map total=%s covered=%s", result.total_symbols, result.covered_count)
    return result


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def security_scan(
    ctx: Context,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
) -> SecurityScanResult:
    """AST-based security scan for common Python vulnerabilities (eval, exec, shell injection, pickle, etc.). Related: get_diagnostics, dead_code_detection."""
    _ = _get_current_backends()
    result = await _security_scan(file_path, file_paths)
    _LOGGER.debug("security_scan files=%s findings=%s", result.files_scanned, result.total_findings)
    return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def security_autofix(
    ctx: Context,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Rewrite unsafe yaml.load() calls (SEC022) to yaml.safe_load(). Targets the literal yaml.load attribute call; calls that already pass an explicit Loader= are skipped (reported in the description). Defaults to preview mode (apply=False). Behavior-changing: safe_load rejects arbitrary tags/object construction that load permits. Related: security_scan."""
    app = _get_current_backends()
    result = await _security_autofix(app.pyright, file_path, file_paths, apply)
    _LOGGER.debug("security_autofix edits=%s applied=%s", len(result.edits), result.applied)
    return result


@mcp.tool(annotations=_DESTRUCTIVE)
@_tool_error_boundary
async def structural_replace(
    ctx: Context,
    pattern: str,
    replacement: str,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Find structural matches with a LibCST matcher pattern and rewrite them. The pattern uses the same matcher DSL as structural_search (e.g. m.Call(func=m.Attribute(value=m.Name('logger'), attr=m.Name('warn')), args=[m.SaveMatchedNode(m.ZeroOrMore(m.Arg()), 'a')])); capture sub-nodes with m.SaveMatchedNode(matcher, 'name') and reference them in the replacement template as $name (e.g. 'logger.warning($a)'). Expression-position matches only. Requires file_path or file_paths; defaults to preview mode (apply=False). Related: structural_search, restructure."""
    app = _get_current_backends()
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


@mcp.tool(annotations=_READONLY)
@_tool_error_boundary
async def server_status(ctx: Context) -> ServerStatus:
    """Report read-only server health: version, known workspace roots, and per-workspace backend liveness (Pyright subprocess up, Jedi/rope ready). Use to tell whether results came from a healthy Pyright or a degraded Jedi fallback. Works even when no workspace is loaded. Probes are cheap and non-blocking. Related: list_environments, restart_server."""
    status = _build_server_status(_get_multi_context(ctx))
    _LOGGER.debug("server_status workspaces=%s degraded=%s", len(status.active_workspaces), status.degraded)
    return status


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
