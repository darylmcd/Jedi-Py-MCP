"""Request-scoped backend resolution and MCP tool error handling."""

from __future__ import annotations

import contextvars
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.util.shared import validate_identifier, validate_workspace_path
from python_refactor_mcp.workspace_registry import WorkspaceBackends, WorkspaceRegistry

# Preserve the established operational sink while moving its implementation out
# of the server shell. Logger names are routing contracts for host deployments.
_LOGGER = logging.getLogger("python_refactor_mcp.server")

# Parameters that contain file paths requiring workspace boundary validation.
# Order is deliberate: when a tool accepts multiple path params, the first
# entry present in kwargs anchors workspace resolution. Source/subject paths
# come before destination paths so move/copy tools resolve to the source
# workspace rather than the destination.
PATH_PARAMS: tuple[str, ...] = (
    "file_path",
    "source_file",
    "source_path",
    "root_path",
    "destination_file",
    "destination_package",
)
_LIST_PATH_PARAMS: tuple[str, ...] = ("file_paths",)

# Parameters that must be valid Python identifiers.
IDENTIFIER_PARAMS: tuple[str, ...] = (
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


@dataclass(slots=True)
class MultiWorkspaceContext:
    """Lifespan context holding the workspace registry."""

    registry: WorkspaceRegistry
    cli_workspace_root: Path | None


# Set by ``tool_error_boundary`` so tool delegates can use the backends selected
# for their current request without threading another parameter through the MCP
# schema-visible signature.
_current_backends: contextvars.ContextVar[WorkspaceBackends] = contextvars.ContextVar("_current_backends")


def get_current_backends() -> WorkspaceBackends:
    """Return the backends selected for the current tool call."""
    try:
        return _current_backends.get()
    except LookupError:
        raise RuntimeError(
            "No workspace backends available. Ensure the tool call was dispatched through tool_error_boundary."
        ) from None


def get_multi_context(ctx: Context) -> MultiWorkspaceContext:
    """Extract the validated lifespan context from an MCP request context."""
    request_context = getattr(ctx, "request_context", None)
    if request_context is None:
        raise RuntimeError("MCP context is missing request_context.")

    lifespan_context = getattr(request_context, "lifespan_context", None)
    if not isinstance(lifespan_context, MultiWorkspaceContext):
        raise RuntimeError("MCP context is missing a valid MultiWorkspaceContext lifespan payload.")

    return lifespan_context


async def _resolve_backends(ctx: Context | None, kwargs: dict[str, Any]) -> WorkspaceBackends | None:
    """Resolve the backends for a tool call from its context and arguments."""
    if ctx is None:
        return None

    multi_ctx = get_multi_context(ctx)
    registry = multi_ctx.registry

    primary_path: str | None = None
    for param_name in PATH_PARAMS:
        value = kwargs.get(param_name)
        if isinstance(value, str):
            primary_path = value
            break
    if primary_path is None:
        for param_name in _LIST_PATH_PARAMS:
            values = kwargs.get(param_name)
            if isinstance(values, list) and values:
                primary_path = next((value for value in values if isinstance(value, str)), None)
                if primary_path is not None:
                    break
    if primary_path is None:
        nested_paths = _transaction_step_paths(kwargs)
        if nested_paths:
            primary_path = nested_paths[0]

    if primary_path is not None:
        return await registry.get_backends(primary_path)

    backends = registry.get_most_recent()
    if backends is None and multi_ctx.cli_workspace_root is not None:
        backends = await registry.get_backends(str(multi_ctx.cli_workspace_root / "__fallback__"))
    return backends


def _validate_params(kwargs: dict[str, Any], workspace_root: Path) -> None:
    """Validate and normalize path and identifier parameters in place."""
    for param_name in PATH_PARAMS:
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

    for param_name in IDENTIFIER_PARAMS:
        value = kwargs.get(param_name)
        if isinstance(value, str):
            validate_identifier(value, param_name)


def tool_error_boundary(
    func: Callable[..., Awaitable[Any]],
) -> Callable[..., Awaitable[Any]]:
    """Resolve request backends and translate anticipated backend failures."""

    @wraps(func)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        ctx = args[0] if args else kwargs.get("ctx")
        backends = await _resolve_backends(ctx, kwargs)

        token = _current_backends.set(backends) if backends is not None else None
        try:
            if backends is not None:
                _validate_params(kwargs, backends.config.workspace_root)
            else:
                for param_name in IDENTIFIER_PARAMS:
                    value = kwargs.get(param_name)
                    if isinstance(value, str):
                        validate_identifier(value, param_name)

            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            except BackendError as exc:
                raise ToolError(f"[{exc.code}] {exc}") from exc
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                _LOGGER.debug("%s completed in %.1fms", func.__name__, elapsed_ms)
        finally:
            if token is not None:
                _current_backends.reset(token)

    return _wrapped
