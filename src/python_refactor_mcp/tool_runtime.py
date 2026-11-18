"""Request-scoped backend resolution and MCP tool error handling."""

from __future__ import annotations

import contextvars
import logging
import time
import traceback
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from python_refactor_mcp.errors import BackendError, ToolInputError, WorkspaceResolutionError
from python_refactor_mcp.models import TransactionStepArgs
from python_refactor_mcp.util.shared import (
    resolve_workspace_dir,
    validate_identifier,
    validate_workspace_path,
)
from python_refactor_mcp.workspace_registry import WorkspaceBackends, WorkspaceRegistry

# Preserve the established operational sink while moving its implementation out
# of the server shell. Logger names are routing contracts for host deployments.
_LOGGER = logging.getLogger("python_refactor_mcp.server")

# Parameters that contain file paths requiring workspace boundary validation.
# Order is deliberate: when a tool accepts multiple path params, the first
# entry present in kwargs anchors workspace resolution, and every present
# entry must resolve to that same workspace (a nested root is a distinct one). Source/subject paths
# come before destination paths so move/copy tools resolve to the source
# workspace rather than the destination. Every entry (and each list/transaction
# path) must be absolute: these values choose the workspace, so no workspace
# exists yet to anchor a relative value, and the server cwd is not a contract.
PATH_PARAMS: tuple[str, ...] = (
    "file_path",
    "source_file",
    "source_path",
    "stub_file",
    "root_path",
    "destination_file",
    "destination_package",
)
_LIST_PATH_PARAMS: tuple[str, ...] = ("file_paths",)

# List parameters whose items are models carrying a ``file_path`` (``TextEdit``,
# ``SymbolAnchor``). Each item's path is validated, anchors and is rewritten
# exactly like a scalar ``file_path``; ``refactor_transaction`` ``steps`` get
# the same treatment through their ``args``.
NESTED_PATH_PARAMS: tuple[str, ...] = ("edits", "symbols")

# Directory-typed parameters requiring workspace boundary validation. Unlike
# PATH_PARAMS these are documented as workspace-relative, so a relative value
# resolves against the workspace root (not the process cwd), and they never
# anchor backend resolution: an output directory says where results go, not
# which workspace the call targets.
DIR_PARAMS: tuple[str, ...] = ("output_dir",)

# Parameters that must be valid Python identifiers.
IDENTIFIER_PARAMS: tuple[str, ...] = (
    "base_class_name",
    "class_name",
    "collaborator_attribute",
    "destination_attr",
    "new_name",
    "new_class_name",
    "function_name",
    "method_name",
    "variable_name",
    "parameter_name",
    "factory_name",
    "classname",
    "protocol_name",
    "symbol_name",
)
_LIST_IDENTIFIER_PARAMS: tuple[str, ...] = ("class_names", "members")


def _transaction_step_args(kwargs: dict[str, Any]) -> list[TransactionStepArgs]:
    """Return the mutable argument models of ``refactor_transaction`` steps in request order.

    The SDK validates ``steps`` into step models before the boundary runs, so
    every step carries a :class:`TransactionStepArgs`. Anything else is a
    wiring defect and raises instead of being skipped: a skipped step would
    bypass the workspace, absolute-path, and identifier checks below.
    """
    steps = kwargs.get("steps")
    if steps is None:
        return []
    if not isinstance(steps, list):
        raise TypeError(f"refactor_transaction steps must be a list of step models, got {type(steps).__name__}")

    step_args: list[TransactionStepArgs] = []
    for index, step in enumerate(steps):
        args = getattr(step, "args", None)
        if not isinstance(args, TransactionStepArgs):
            raise TypeError(f"refactor_transaction steps[{index}] is not a validated step model")
        step_args.append(args)
    return step_args


def _nested_path_models(kwargs: dict[str, Any]) -> list[tuple[str, Any]]:
    """Return ``(parameter label, model)`` for every model that carries a nested ``file_path``.

    Covers the ``NESTED_PATH_PARAMS`` list parameters, then the ``refactor_transaction``
    step arguments, in request order. Like ``_transaction_step_args`` it raises
    ``TypeError`` for an item that is not a validated model with a string
    ``file_path``: a skipped item would bypass the workspace and absolute-path checks.
    """
    found: list[tuple[str, Any]] = []
    for param_name in NESTED_PATH_PARAMS:
        items = kwargs.get(param_name)
        if items is None:
            continue
        if not isinstance(items, list):
            raise TypeError(f"{param_name} must be a list of validated models, got {type(items).__name__}")
        for index, item in enumerate(items):
            if not isinstance(getattr(item, "file_path", None), str):
                raise TypeError(f"{param_name}[{index}] is not a validated model with a file_path")
            found.append((f"{param_name}[{index}].file_path", item))
    found.extend(
        (f"steps[{index}].args.file_path", args) for index, args in enumerate(_transaction_step_args(kwargs))
    )
    return found


class WorkspaceUse(Enum):
    """What a tool needs from the workspace its explicit paths select.

    ``BACKENDS`` resolves (and lazily starts) the workspace's Pyright, Jedi and
    rope backends. ``ROOT_ONLY`` is for a tool that only validates and reads
    caller paths: the boundary derives the workspace root from those paths, never
    resolves or starts a backend, and so also works with zero or several live
    backends. ``NONE`` is for a tool that reports server state and needs no
    workspace: the boundary resolves nothing, so it works with none live.
    """

    BACKENDS = "backends"
    ROOT_ONLY = "root_only"
    NONE = "none"


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


def _workspace_path_args(kwargs: dict[str, Any]) -> list[tuple[str, str]]:
    """Return ``(parameter label, value)`` for every explicit workspace-selecting path.

    Order is the anchor order: ``PATH_PARAMS`` entries, then ``file_paths``
    elements, then paths nested in ``NESTED_PATH_PARAMS`` models and
    ``refactor_transaction`` step args. Non-string scalar and list values are
    skipped; ``_validate_params`` rejects them.
    """
    found: list[tuple[str, str]] = []
    for param_name in PATH_PARAMS:
        value = kwargs.get(param_name)
        if isinstance(value, str):
            found.append((param_name, value))
    for param_name in _LIST_PATH_PARAMS:
        values = kwargs.get(param_name)
        if isinstance(values, list):
            found.extend((param_name, value) for value in values if isinstance(value, str))
    found.extend((label, model.file_path) for label, model in _nested_path_models(kwargs))
    return found


def _require_single_workspace(registry: WorkspaceRegistry, kwargs: dict[str, Any]) -> None:
    """Reject a request whose explicit paths resolve to more than one workspace.

    Containment in the selected root is not enough: a nested project root lies
    inside its enclosing checkout yet is a different workspace with its own
    backends and configuration. Resolving roots is a pure path walk, so a
    rejected request neither starts a backend nor evicts a live workspace. The
    anchor's own resolution error propagates; a later path with no enclosing
    root is left to the containment check so it keeps its typed input error.
    """
    roots: dict[Path, str] = {}
    for index, (label, value) in enumerate(_workspace_path_args(kwargs)):
        try:
            root = registry.resolve_workspace_root(Path(value))
        except WorkspaceResolutionError:
            if index == 0:
                raise
            continue
        roots.setdefault(root, f"{label}={value}")
    if len(roots) > 1:
        located = "; ".join(f"{described} -> {root}" for root, described in roots.items())
        raise ToolInputError(
            f"Paths span multiple workspaces ({located}); split the call into one call per workspace"
        )


async def _resolve_backends(ctx: Context | None, kwargs: dict[str, Any]) -> WorkspaceBackends | None:
    """Resolve the backends for a tool call from its context and arguments.

    A call that names no workspace-selecting path resolves only to the sole workspace
    a path-bearing request already selected; anything else raises
    ``AmbiguousWorkspaceError`` instead of guessing.
    """
    if ctx is None:
        return None

    multi_ctx = get_multi_context(ctx)
    registry = multi_ctx.registry

    paths = [value for _label, value in _workspace_path_args(kwargs)]
    if paths:
        _require_single_workspace(registry, kwargs)
        return await registry.get_backends(paths[0])

    return registry.implicit_workspace()


def _resolve_workspace_root(ctx: Context | None, kwargs: dict[str, Any]) -> Path | None:
    """Resolve only the workspace root selected by a call's explicit paths, starting no backend.

    Returns ``None`` when there is no context or no selecting path. Rejects mixed
    workspaces exactly like ``_resolve_backends``; the first path's resolution
    error propagates.
    """
    if ctx is None:
        return None

    registry = get_multi_context(ctx).registry
    paths = [value for _label, value in _workspace_path_args(kwargs)]
    if not paths:
        return None

    _require_single_workspace(registry, kwargs)
    return registry.resolve_workspace_root(Path(paths[0]))


def _require_absolute(value: str, param_label: str) -> None:
    """Raise ``ToolInputError`` naming *param_label* when *value* is not an absolute path."""
    if not Path(value).is_absolute():
        raise ToolInputError(f"'{value}' is not an absolute path (parameter: {param_label})")


def _reject_relative_paths(kwargs: dict[str, Any]) -> None:
    """Reject relative workspace-selecting path arguments before backend resolution.

    Runs before ``_resolve_backends`` so a relative value can never select (or
    lazily initialize) a workspace through the server process cwd. ``~/x`` counts
    as relative; on Windows a POSIX-rooted ``/x`` is not absolute. Non-string
    values are left to ``_validate_params``.
    """
    for label, value in _workspace_path_args(kwargs):
        _require_absolute(value, label)


def _validate_params(kwargs: dict[str, Any], workspace_root: Path) -> None:
    """Validate and normalize path and identifier parameters in place."""
    for param_name in PATH_PARAMS:
        value = kwargs.get(param_name)
        if isinstance(value, str):
            kwargs[param_name] = validate_workspace_path(value, workspace_root)

    for param_name in _LIST_PATH_PARAMS:
        values = kwargs.get(param_name)
        if isinstance(values, list):
            if not all(isinstance(value, str) for value in values):
                raise ToolInputError(f"{param_name} must contain only strings")
            kwargs[param_name] = [validate_workspace_path(value, workspace_root) for value in values]

    for param_name in DIR_PARAMS:
        value = kwargs.get(param_name)
        if isinstance(value, str):
            kwargs[param_name] = resolve_workspace_dir(value, workspace_root)

    for _label, model in _nested_path_models(kwargs):
        model.file_path = validate_workspace_path(model.file_path, workspace_root)

    _validate_identifiers(kwargs)
    for args in _transaction_step_args(kwargs):
        _validate_identifiers(args.model_dump())


def _validate_identifiers(kwargs: dict[str, Any]) -> None:
    """Validate scalar and list-valued identifier parameters in one argument object."""
    for param_name in IDENTIFIER_PARAMS:
        value = kwargs.get(param_name)
        if isinstance(value, str):
            validate_identifier(value, param_name)
    for param_name in _LIST_IDENTIFIER_PARAMS:
        values = kwargs.get(param_name)
        if isinstance(values, list):
            if not all(isinstance(value, str) for value in values):
                raise ToolInputError(f"{param_name} must contain only strings")
            for value in values:
                validate_identifier(value, param_name)


def _safe_failure_diagnostics(exc: BackendError) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return exception types and path-free traceback locations for structured logs."""
    exception_types: list[str] = []
    traceback_locations: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc

    while current is not None and id(current) not in seen and len(exception_types) < 16:
        seen.add(id(current))
        current_type = type(current)
        exception_types.append(f"{current_type.__module__}.{current_type.__qualname__}")
        traceback_locations.extend(
            f"{frame.name}:{frame.lineno}"
            for frame in traceback.extract_tb(current.__traceback__)[-16:]
        )
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )

    return tuple(exception_types), tuple(traceback_locations[-32:])


def _translate_backend_error(exc: BackendError, tool_name: str) -> ToolError:
    """Record redacted diagnostics and build the stable caller-facing error."""
    failure_id = uuid.uuid4().hex[:12]
    exception_types, traceback_locations = _safe_failure_diagnostics(exc)
    _LOGGER.error(
        "Backend failure id=%s tool=%s code=%s",
        failure_id,
        tool_name,
        exc.code,
        extra={
            "event": "tool_backend_failure",
            "failure_id": failure_id,
            "tool_name": tool_name,
            "error_code": exc.code,
            "exception_types": exception_types,
            "traceback_locations": traceback_locations,
        },
    )
    return ToolError(f"[{exc.code}] {exc.caller_summary} Failure ID: {failure_id}.")


def _translate_input_error(exc: ToolInputError, tool_name: str) -> ToolError:
    """Build the caller-facing error for a rejected caller input.

    The message is caller-safe by contract (see ``ToolInputError``), so it is
    surfaced verbatim. A rejected input is not a server failure: it is logged at
    DEBUG without a traceback or failure id.
    """
    _LOGGER.debug(
        "Rejected tool input tool=%s code=%s",
        tool_name,
        exc.code,
        extra={
            "event": "tool_input_error",
            "tool_name": tool_name,
            "error_code": exc.code,
        },
    )
    return ToolError(f"[{exc.code}] {exc}")


def tool_error_boundary(
    func: Callable[..., Awaitable[Any]],
    *,
    workspace: WorkspaceUse = WorkspaceUse.BACKENDS,
) -> Callable[..., Awaitable[Any]]:
    """Resolve the request workspace and translate anticipated caller-input and backend failures.

    *workspace* selects what is resolved: the backends (default), only the
    validated workspace root (``WorkspaceUse.ROOT_ONLY``), or nothing
    (``WorkspaceUse.NONE``).
    """

    @wraps(func)
    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        token: contextvars.Token[WorkspaceBackends] | None = None
        try:
            ctx = args[0] if args else kwargs.get("ctx")
            _reject_relative_paths(kwargs)
            backends: WorkspaceBackends | None = None
            workspace_root: Path | None
            if workspace is WorkspaceUse.NONE:
                workspace_root = None
            elif workspace is WorkspaceUse.ROOT_ONLY:
                workspace_root = _resolve_workspace_root(ctx, kwargs)
            else:
                backends = await _resolve_backends(ctx, kwargs)
                workspace_root = backends.config.workspace_root if backends is not None else None
            token = _current_backends.set(backends) if backends is not None else None

            if workspace_root is not None:
                _validate_params(kwargs, workspace_root)
            else:
                _validate_identifiers(kwargs)
                for step_args in _transaction_step_args(kwargs):
                    _validate_identifiers(step_args.model_dump())

            return await func(*args, **kwargs)
        except ToolInputError as exc:
            raise _translate_input_error(exc, func.__name__) from None
        except BackendError as exc:
            raise _translate_backend_error(exc, func.__name__) from None
        finally:
            if token is not None:
                _current_backends.reset(token)
            elapsed_ms = (time.perf_counter() - start) * 1000
            _LOGGER.debug("%s completed in %.1fms", func.__name__, elapsed_ms)

    return _wrapped
