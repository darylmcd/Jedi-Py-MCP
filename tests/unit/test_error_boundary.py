"""Unit tests for the tool error boundary and its extracted helpers.

These pin the observable behavior of the error boundary so the
``_resolve_backends`` / ``_validate_params`` decomposition stays a pure
refactor: backend resolution, the per-call ContextVar, path + identifier
validation, timing instrumentation, and ``BackendError`` -> ``ToolError``
translation.
"""

from __future__ import annotations

import contextlib
import inspect
import logging
import os
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from python_refactor_mcp import tool_runtime
from python_refactor_mcp.backends.rope_backend import RopeBackend
from python_refactor_mcp.config import TOOL_PROFILES
from python_refactor_mcp.errors import (
    AmbiguousWorkspaceError,
    BackendError,
    ConfigError,
    JediError,
    LspFeatureUnsupportedError,
    PyrightError,
    RopeError,
    ToolInputError,
    WorkspaceResolutionError,
)
from python_refactor_mcp.models import Position, Range, RenameStep, RenameStepArgs, SymbolAnchor, TextEdit
from python_refactor_mcp.tool_registry import TOOL_RECORDS, build_tools, diff_preview
from python_refactor_mcp.tool_runtime import (
    DIR_PARAMS,
    PATH_PARAMS,
    MultiWorkspaceContext,
    _resolve_backends,
    _validate_params,
    get_current_backends,
    get_multi_context,
    tool_error_boundary,
)
from python_refactor_mcp.tools import composite
from python_refactor_mcp.util.shared import validate_workspace_path
from python_refactor_mcp.workspace_registry import WorkspaceBackends, WorkspaceRegistry


def _rename_step(file_path: str, new_name: str = "renamed") -> RenameStep:
    """Build a schema-validated rename step, as the SDK hands it to the boundary."""
    return RenameStep(
        tool="rename_symbol",
        args=RenameStepArgs(file_path=file_path, line=0, character=0, new_name=new_name),
    )


def _backends(root: Path) -> WorkspaceBackends:
    """Build a WorkspaceBackends whose config.workspace_root is *root*."""
    config = MagicMock()
    config.workspace_root = root
    return WorkspaceBackends(
        config=config,
        pyright=MagicMock(),
        jedi=MagicMock(),
        rope=MagicMock(),
    )


def _ctx_with(multi_ctx: MultiWorkspaceContext) -> SimpleNamespace:
    """Build a fake MCP Context carrying *multi_ctx* as the lifespan payload."""
    session = MagicMock()
    return SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=multi_ctx, session=session),
    )


# ── _resolve_backends ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_backends_uses_primary_path(tmp_path: Path) -> None:
    """The first present _PATH_PARAMS entry anchors registry resolution."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    ctx = _ctx_with(multi_ctx)

    resolved = await _resolve_backends(ctx, {"file_path": str(root / "mod.py")})

    assert resolved is backends
    registry.get_backends.assert_awaited_once_with(str(root / "mod.py"))


@pytest.mark.asyncio
async def test_resolve_backends_list_path_fallback(tmp_path: Path) -> None:
    """When no scalar path param is present, the first list-path entry anchors."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    ctx = _ctx_with(multi_ctx)

    resolved = await _resolve_backends(ctx, {"file_paths": [str(root / "a.py"), str(root / "b.py")]})

    assert resolved is backends
    registry.get_backends.assert_awaited_once_with(str(root / "a.py"))


@pytest.mark.asyncio
async def test_resolve_backends_uses_nested_transaction_path(tmp_path: Path) -> None:
    """refactor_transaction resolves from its first nested step file path."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    ctx = _ctx_with(multi_ctx)
    target = root / "mod.py"

    resolved = await _resolve_backends(
        ctx,
        {"steps": [_rename_step(str(target))]},
    )

    assert resolved is backends
    registry.get_backends.assert_awaited_once_with(str(target))


def _live_registry_ctx(
    tmp_path: Path, *, selected: tuple[bool, ...]
) -> tuple[SimpleNamespace, WorkspaceRegistry, list[WorkspaceBackends]]:
    """Build a ctx over a real registry holding one live mocked workspace per *selected* flag."""
    registry = _BackendlessRegistry()
    live: list[WorkspaceBackends] = []
    for index, flag in enumerate(selected):
        root = (tmp_path / f"ws{index}").resolve()
        backends = _backends(root)
        backends.selected = flag
        backends.last_accessed = 1.0
        registry._workspaces[root] = backends
        live.append(backends)
    return _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=None)), registry, live


@pytest.mark.asyncio
async def test_resolve_backends_no_path_rejects_several_live_workspaces(tmp_path: Path) -> None:
    """A path-less call never picks among several live workspaces, however recently each was used."""
    ctx, _registry, live = _live_registry_ctx(tmp_path, selected=(True, True))
    live[0].last_accessed = 99.0

    with pytest.raises(AmbiguousWorkspaceError, match=r"2 workspaces are live.*root_path") as excinfo:
        await _resolve_backends(ctx, {"limit": 5})

    for backends in live:
        assert str(backends.config.workspace_root) in str(excinfo.value)


@pytest.mark.asyncio
async def test_resolve_backends_no_path_rejects_the_prewarmed_root_nothing_selected(tmp_path: Path) -> None:
    """A path-less call does not fall back to the pre-warmed CLI root no path-bearing call has selected."""
    ctx, _registry, _live = _live_registry_ctx(tmp_path, selected=(False,))

    with pytest.raises(AmbiguousWorkspaceError, match=r"pre-warmed, not selected.*root_path"):
        await _resolve_backends(ctx, {})


@pytest.mark.asyncio
async def test_resolve_backends_no_path_rejects_a_cold_registry(tmp_path: Path) -> None:
    """With no live workspace a path-less call raises the coded error instead of a RuntimeError."""
    ctx, _registry, _live = _live_registry_ctx(tmp_path, selected=())

    with pytest.raises(AmbiguousWorkspaceError, match=r"no workspace is live.*root_path"):
        await _resolve_backends(ctx, {})


@pytest.mark.asyncio
async def test_resolve_backends_no_path_uses_and_touches_the_sole_selected_workspace(tmp_path: Path) -> None:
    """Once a path-bearing call selected the only live workspace, path-less calls resolve to it."""
    ctx, _registry, live = _live_registry_ctx(tmp_path, selected=(True,))

    resolved = await _resolve_backends(ctx, {"limit": 5})

    assert resolved is live[0]
    assert live[0].last_accessed > 1.0


@pytest.mark.asyncio
async def test_wrapper_surfaces_ambiguous_workspace_code_before_any_tool_runs(tmp_path: Path) -> None:
    """The boundary renders [AMBIGUOUS_WORKSPACE] and a mutating tool body (apply) never runs."""
    ctx, _registry, _live = _live_registry_ctx(tmp_path, selected=(True, True))
    called = False

    @tool_error_boundary
    async def fix_module_names(ctx: object, apply: bool = False) -> str:
        nonlocal called
        called = True
        return "renamed"

    with pytest.raises(ToolError, match=r"^\[AMBIGUOUS_WORKSPACE\] .*root_path"):
        await fix_module_names(ctx, apply=True)
    assert called is False


@pytest.mark.asyncio
@pytest.mark.parametrize("selected", [(), (False,), (True, True)])
async def test_none_mode_tool_runs_without_resolving_a_workspace(tmp_path: Path, selected: tuple[bool, ...]) -> None:
    """A workspace-less tool (server_status) works with a cold, pre-warm-only or multi-workspace registry and no ctx."""
    ctx, _registry, _live = _live_registry_ctx(tmp_path, selected=selected)

    async def status_like(ctx: object) -> str:
        assert tool_runtime._current_backends.get(None) is None
        return "ok"

    wrapped = tool_error_boundary(status_like, workspace=tool_runtime.WorkspaceUse.NONE)

    assert await wrapped(ctx) == "ok"
    assert await wrapped(None) == "ok"


@pytest.mark.asyncio
async def test_resolve_backends_rejects_invalid_multi_ctx() -> None:
    """A malformed supplied lifespan context preserves its specific diagnosis."""
    ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=object(), session=MagicMock()))

    with pytest.raises(RuntimeError, match="valid MultiWorkspaceContext lifespan payload"):
        await _resolve_backends(ctx, {"file_path": "/somewhere/mod.py"})


@pytest.mark.asyncio
async def test_resolve_backends_none_when_ctx_is_none() -> None:
    """No ctx at all -> no backends."""
    resolved = await _resolve_backends(None, {"file_path": "/x.py"})
    assert resolved is None


@pytest.mark.asyncio
async def test_resolve_backends_does_not_request_deprecated_roots(tmp_path: Path) -> None:
    """Workspace resolution relies on request paths, not deprecated MCP roots."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    ctx = _ctx_with(multi_ctx)
    ctx.request_context.session.list_roots = AsyncMock()

    resolved = await _resolve_backends(ctx, {"file_path": str(root / "mod.py")})

    assert resolved is backends
    ctx.request_context.session.list_roots.assert_not_awaited()


# ── _validate_params ─────────────────────────────────────────────────────


def test_validate_params_resolves_path_within_workspace(tmp_path: Path) -> None:
    """A path under the workspace root is resolved to an absolute string."""
    kwargs = {"file_path": str(tmp_path / "pkg" / "mod.py")}
    _validate_params(kwargs, tmp_path)
    assert kwargs["file_path"] == str((tmp_path / "pkg" / "mod.py").resolve())


def test_validate_params_rejects_path_outside_workspace(tmp_path: Path) -> None:
    """A path outside the workspace root raises ValueError."""
    other = tmp_path / "outside"
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with pytest.raises(ValueError, match="outside the workspace root"):
        _validate_params({"file_path": str(other / "mod.py")}, workspace)


def test_validate_params_validates_list_paths(tmp_path: Path) -> None:
    """List-path params are validated and resolved element-wise."""
    kwargs = {"file_paths": [str(tmp_path / "a.py"), str(tmp_path / "b.py")]}
    _validate_params(kwargs, tmp_path)
    assert kwargs["file_paths"] == [
        str((tmp_path / "a.py").resolve()),
        str((tmp_path / "b.py").resolve()),
    ]


def test_validate_params_rejects_non_string_list_path(tmp_path: Path) -> None:
    """Malformed path lists fail instead of silently dropping entries."""
    with pytest.raises(ValueError, match="file_paths must contain only strings"):
        _validate_params({"file_paths": [str(tmp_path / "a.py"), 3]}, tmp_path)


def test_validate_params_resolves_nested_transaction_paths(tmp_path: Path) -> None:
    """Every transaction step path is normalized against the selected workspace."""
    steps = [_rename_step(str(tmp_path / "a.py")), _rename_step(str(tmp_path / "b.py"))]
    kwargs: dict[str, object] = {"steps": steps}

    _validate_params(kwargs, tmp_path)

    assert [step.args.file_path for step in steps] == [
        str((tmp_path / "a.py").resolve()),
        str((tmp_path / "b.py").resolve()),
    ]


def test_validate_params_resolves_relative_dir_against_workspace(tmp_path: Path) -> None:
    """A relative directory param anchors at the workspace root, not the process cwd."""
    kwargs = {"output_dir": "stubs"}
    _validate_params(kwargs, tmp_path)
    assert kwargs["output_dir"] == str((tmp_path / "stubs").resolve())


def test_validate_params_rejects_dir_outside_workspace(tmp_path: Path) -> None:
    """Absolute and relative directory params escaping the workspace are rejected."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with pytest.raises(ToolInputError, match="outside the workspace root"):
        _validate_params({"output_dir": str(tmp_path / "outside")}, workspace)
    with pytest.raises(ToolInputError, match="outside the workspace root"):
        _validate_params({"output_dir": "../outside"}, workspace)


def test_dir_params_are_disjoint_from_backend_anchoring_path_params() -> None:
    """Directory params never anchor backend resolution."""
    assert not set(DIR_PARAMS) & set(PATH_PARAMS)


@pytest.mark.asyncio
async def test_every_directory_typed_tool_param_is_validated() -> None:
    """Drift guard: every registered ``*_dir``/``*_directory`` parameter is in DIR_PARAMS."""
    directory_params: set[str] = set()
    for profile in TOOL_PROFILES:
        mcp = MCPServer(
            f"dir-param drift guard ({profile})",
            tools=build_tools(profile),
        )
        for tool in await mcp.list_tools():
            properties = tool.input_schema.get("properties", {})
            directory_params.update(name for name in properties if name.endswith(("_dir", "_directory")))
    assert directory_params, "expected at least one directory-typed tool parameter (output_dir)"
    assert directory_params <= set(DIR_PARAMS), (
        f"directory params missing from DIR_PARAMS: {sorted(directory_params - set(DIR_PARAMS))}"
    )


def test_validate_params_rejects_bad_identifier(tmp_path: Path) -> None:
    """An invalid identifier parameter raises ValueError."""
    with pytest.raises(ValueError, match="not a valid Python identifier"):
        _validate_params({"new_name": "1bad"}, tmp_path)


def test_validate_params_accepts_valid_identifier(tmp_path: Path) -> None:
    """A valid identifier passes through untouched."""
    kwargs = {"new_name": "good_name"}
    _validate_params(kwargs, tmp_path)
    assert kwargs["new_name"] == "good_name"


def test_validate_params_rejects_bad_list_identifier(tmp_path: Path) -> None:
    """Identifier lists receive the same validation as scalar names."""
    with pytest.raises(ValueError, match="not a valid Python identifier"):
        _validate_params({"class_names": ["Good", "1bad"]}, tmp_path)


def test_validate_params_rejects_non_string_list_identifier(tmp_path: Path) -> None:
    """Malformed identifier lists fail instead of silently dropping entries."""
    with pytest.raises(ValueError, match="class_names must contain only strings"):
        _validate_params({"class_names": ["Good", 3]}, tmp_path)


def test_validate_params_rejects_bad_nested_transaction_identifier(tmp_path: Path) -> None:
    """Transaction steps cannot bypass top-level identifier validation."""
    kwargs = {"steps": [_rename_step(str(tmp_path / "a.py"), new_name="1bad")]}
    with pytest.raises(ValueError, match="not a valid Python identifier"):
        _validate_params(kwargs, tmp_path)


def test_validate_params_refuses_unvalidated_transaction_step(tmp_path: Path) -> None:
    """A raw step dict is a wiring defect: it raises instead of silently skipping path checks."""
    kwargs = {"steps": [{"tool": "rename_symbol", "args": {"file_path": "../escape.py"}}]}
    with pytest.raises(TypeError, match=r"steps\[0\] is not a validated step model"):
        _validate_params(kwargs, tmp_path)


# ── _tool_error_boundary (wrapper integration) ───────────────────────────


@pytest.mark.asyncio
async def test_nested_workspace_call_rejects_paths_in_enclosing_workspace(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    nested = root / ".worktrees" / "branch"
    nested.mkdir(parents=True)
    (nested / ".git").touch()
    registry = WorkspaceRegistry()
    await registry.set_roots([root])
    registry._workspaces = {root: _backends(root), nested: _backends(nested)}
    ctx = _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=root))

    @tool_error_boundary
    async def diagnostic_tool(ctx: object, file_paths: list[str]) -> Path:
        return get_current_backends().config.workspace_root

    nested_file = str(nested / "module.py")
    assert await diagnostic_tool(ctx, file_paths=[nested_file]) == nested

    with pytest.raises(ToolError, match="Paths span multiple workspaces"):
        await diagnostic_tool(ctx, file_paths=[nested_file, str(root / "module.py")])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_type", "code", "caller_summary"),
    [
        (BackendError, "BACKEND", BackendError.caller_summary),
        (PyrightError, "PYRIGHT_BACKEND", PyrightError.caller_summary),
        (
            LspFeatureUnsupportedError,
            "LSP_UNSUPPORTED",
            LspFeatureUnsupportedError.caller_summary,
        ),
        (JediError, "JEDI_BACKEND", JediError.caller_summary),
        (RopeError, "ROPE_BACKEND", RopeError.caller_summary),
        (ConfigError, "CONFIG", ConfigError.caller_summary),
        (
            WorkspaceResolutionError,
            "WORKSPACE_RESOLUTION",
            WorkspaceResolutionError.caller_summary,
        ),
    ],
)
async def test_wrapper_translates_backend_error(
    tmp_path: Path,
    error_type: type[BackendError],
    code: str,
    caller_summary: str,
) -> None:
    """Each backend error becomes an anticipated, provenance-coded tool error."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    ctx = _ctx_with(multi_ctx)

    @tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        raise error_type("backend boom")

    with pytest.raises(
        ToolError,
        match=rf"^\[{code}\] {caller_summary} Failure ID: [0-9a-f]{{12}}\.$",
    ):
        await tool(ctx, file_path=str(root / "mod.py"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "internal_message",
    [
        r"C:\\Users\\private\\workspace\\module.py: provider exploded",
        "/home/private/workspace/module.py: provider exploded",
        "provider line one\nprovider line two\nprovider line three",
        "api_key=sk-secret-value password=hunter2 bearer=private-token",
    ],
)
async def test_wrapper_redacts_backend_payloads_from_caller_and_logs(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    internal_message: str,
) -> None:
    """Backend payloads never cross the caller or operational logging boundary."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    ctx = _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=None))

    @tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        try:
            raise OSError(internal_message)
        except OSError as cause:
            raise PyrightError(internal_message) from cause

    with (
        caplog.at_level(logging.ERROR, logger="python_refactor_mcp.server"),
        pytest.raises(ToolError) as raised,
    ):
        await tool(ctx, file_path=str(root / "mod.py"))

    assert internal_message not in str(raised.value)
    assert internal_message not in caplog.text
    assert str(raised.value).startswith(f"[PYRIGHT_BACKEND] {PyrightError.caller_summary}")
    record = next(record for record in caplog.records if record.event == "tool_backend_failure")
    assert record.error_code == "PYRIGHT_BACKEND"
    assert record.tool_name == "tool"
    assert record.exception_types == (
        "python_refactor_mcp.errors.PyrightError",
        "builtins.OSError",
    )
    assert all("\\" not in location and "/" not in location for location in record.traceback_locations)


@pytest.mark.asyncio
async def test_wrapper_translates_backend_error_during_resolution(tmp_path: Path) -> None:
    """Workspace/backend initialization failures cannot bypass the MCP boundary."""
    registry = MagicMock()
    registry.get_backends = AsyncMock(
        side_effect=ConfigError(r"invalid provider config at C:\\private\\pyrightconfig.json")
    )
    ctx = _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=None))

    @tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        return "unreachable"

    with pytest.raises(ToolError) as raised:
        await tool(ctx, file_path=str(tmp_path / "mod.py"))

    assert str(raised.value).startswith(f"[CONFIG] {ConfigError.caller_summary}")
    assert "private" not in str(raised.value)


@pytest.mark.asyncio
async def test_wrapper_sets_contextvar_for_tool(tmp_path: Path) -> None:
    """The resolved backends are visible via _get_current_backends inside the tool."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    ctx = _ctx_with(multi_ctx)

    seen: dict[str, object] = {}

    @tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        seen["backends"] = get_current_backends()
        return "ok"

    result = await tool(ctx, file_path=str(root / "mod.py"))

    assert result == "ok"
    assert seen["backends"] is backends


@pytest.mark.asyncio
async def test_wrapper_resets_contextvar_after_call(tmp_path: Path) -> None:
    """The ContextVar is reset after the tool returns (no leak across calls)."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    ctx = _ctx_with(multi_ctx)

    @tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        return "ok"

    await tool(ctx, file_path=str(root / "mod.py"))

    with pytest.raises(RuntimeError, match="No workspace backends available"):
        get_current_backends()


@pytest.mark.asyncio
async def test_wrapper_validates_path_against_resolved_workspace(tmp_path: Path) -> None:
    """A path outside the resolved workspace is rejected before the tool runs."""
    root = tmp_path / "ws"
    root.mkdir()
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    ctx = _ctx_with(multi_ctx)

    called = False

    @tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        nonlocal called
        called = True
        return "ok"

    # get_backends returns the ws-rooted backends, but the path is elsewhere.
    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] File path is outside the workspace root"):
        await tool(ctx, file_path=str(tmp_path / "elsewhere" / "mod.py"))
    assert called is False


@pytest.mark.asyncio
async def test_wrapper_rejects_output_dir_outside_workspace(tmp_path: Path) -> None:
    """An out-of-workspace directory argument is rejected at the tool boundary."""
    root = tmp_path / "ws"
    root.mkdir()
    backends = _backends(root)
    registry = MagicMock()
    registry.implicit_workspace = MagicMock(return_value=backends)
    registry.get_backends = AsyncMock(return_value=backends)
    ctx = _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=None))

    called = False

    @tool_error_boundary
    async def tool(ctx: object, package_name: str, output_dir: str | None = None) -> str:
        nonlocal called
        called = True
        return "ok"

    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] File path is outside the workspace root"):
        await tool(ctx, package_name="requests", output_dir=str(tmp_path / "elsewhere"))
    assert called is False
    # output_dir must not anchor workspace resolution.
    registry.get_backends.assert_not_awaited()


# ── relative workspace-selecting paths (bl-0041) ────────────────────────


def _relative_path_ctx(root: Path) -> tuple[SimpleNamespace, MagicMock]:
    """Build a ctx whose registry would resolve any path to *root*'s backends."""
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    registry.implicit_workspace = MagicMock(return_value=backends)
    return _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=None)), registry


def test_validate_workspace_path_rejects_relative_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Direct callers get an input error instead of a cwd-anchored resolution."""
    (tmp_path / "pkg").mkdir()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ToolInputError, match=r"^File path must be absolute: 'pkg/mod\.py' is relative$"):
        validate_workspace_path("pkg/mod.py", tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("param_name", PATH_PARAMS)
async def test_wrapper_rejects_relative_path_param_before_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    param_name: str,
) -> None:
    """A relative path param is rejected even when the cwd would make it resolve inside the workspace."""
    root = tmp_path / "ws"
    (root / "pkg").mkdir(parents=True)
    monkeypatch.chdir(root)
    ctx, registry = _relative_path_ctx(root)
    called = False

    @tool_error_boundary
    async def tool(ctx: object, **kwargs: str) -> str:
        nonlocal called
        called = True
        return "ok"

    with pytest.raises(ToolError) as raised:
        await tool(ctx, **{param_name: "pkg/mod.py"})

    assert str(raised.value) == f"[INVALID_INPUT] 'pkg/mod.py' is not an absolute path (parameter: {param_name})"
    assert called is False
    registry.get_backends.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrapper_rejects_relative_file_paths_element(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One relative entry in file_paths rejects the call before any workspace is selected."""
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.chdir(root)
    ctx, registry = _relative_path_ctx(root)

    @tool_error_boundary
    async def tool(ctx: object, file_paths: list[str]) -> str:
        return "ok"

    with pytest.raises(
        ToolError,
        match=r"^\[INVALID_INPUT\] 'b\.py' is not an absolute path \(parameter: file_paths\)$",
    ):
        await tool(ctx, file_paths=[str(root / "a.py"), "b.py"])
    registry.get_backends.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrapper_rejects_relative_transaction_step_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A relative nested refactor_transaction path is rejected and located by step index."""
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.chdir(root)
    ctx, registry = _relative_path_ctx(root)

    @tool_error_boundary
    async def tool(ctx: object, steps: list[RenameStep]) -> str:
        return "ok"

    steps = [_rename_step(str(root / "a.py")), _rename_step("b.py")]
    with pytest.raises(
        ToolError,
        match=r"^\[INVALID_INPUT\] 'b\.py' is not an absolute path \(parameter: steps\[1\]\.args\.file_path\)$",
    ):
        await tool(ctx, steps=steps)
    registry.get_backends.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrapper_rejects_home_relative_path(tmp_path: Path) -> None:
    """``~/x`` is not expanded into an absolute path; it counts as relative."""
    ctx, registry = _relative_path_ctx(tmp_path)

    @tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        return "ok"

    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] '~/mod\.py' is not an absolute path"):
        await tool(ctx, file_path="~/mod.py")
    registry.get_backends.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="a POSIX-rooted path is absolute outside Windows")
async def test_wrapper_rejects_posix_rooted_path_on_windows(tmp_path: Path) -> None:
    """On Windows ``/x`` has no drive, so it is not absolute and is rejected."""
    ctx, registry = _relative_path_ctx(tmp_path)

    @tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        return "ok"

    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] '/pkg/mod\.py' is not an absolute path"):
        await tool(ctx, file_path="/pkg/mod.py")
    registry.get_backends.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrapper_still_anchors_relative_output_dir_at_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Directory params stay workspace-relative: they follow an already-chosen workspace."""
    root = tmp_path / "ws"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    ctx, _registry = _relative_path_ctx(root)

    @tool_error_boundary
    async def tool(ctx: object, package_name: str, output_dir: str | None = None) -> str | None:
        return output_dir

    result = await tool(ctx, package_name="requests", output_dir="stubs")

    assert result == str((root / "stubs").resolve())


@pytest.mark.asyncio
async def test_wrapper_records_timing_via_server_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The wrapper emits timing through standard server logging."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    ctx = _ctx_with(multi_ctx)

    @tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        return "ok"

    with caplog.at_level(logging.DEBUG, logger="python_refactor_mcp.server"):
        await tool(ctx, file_path=str(root / "mod.py"))

    assert "tool completed in" in caplog.text


@pytest.mark.asyncio
async def test_wrapper_validates_identifier_without_backends() -> None:
    """Identifier validation runs even when no backends resolve (ctx is None)."""

    @tool_error_boundary
    async def tool(new_name: str) -> str:
        return "ok"

    # No ctx -> backends is None, but identifier validation still applies.
    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] '1bad' is not a valid Python identifier"):
        await tool(new_name="1bad")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_name", ["   ", "class"])
async def test_wrapper_surfaces_invalid_identifier_verbatim_without_error_log(
    caplog: pytest.LogCaptureFixture,
    bad_name: str,
) -> None:
    """Caller-input rejections name the parameter and are not logged as server failures."""

    @tool_error_boundary
    async def tool(new_name: str) -> str:
        return "unreachable"

    with (
        caplog.at_level(logging.DEBUG, logger="python_refactor_mcp.server"),
        pytest.raises(ToolError) as raised,
    ):
        await tool(new_name=bad_name)

    message = str(raised.value)
    assert message.startswith("[INVALID_INPUT] ")
    assert "(parameter: new_name)" in message
    assert "Failure ID" not in message
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]
    record = next(record for record in caplog.records if getattr(record, "event", None) == "tool_input_error")
    assert record.levelno == logging.DEBUG
    assert record.tool_name == "tool"
    assert record.error_code == "INVALID_INPUT"
    assert record.exc_info is None


@pytest.mark.asyncio
async def test_wrapper_surfaces_tool_input_error_raised_by_tool(tmp_path: Path) -> None:
    """A ToolInputError raised inside a tool body is surfaced verbatim, not redacted."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    ctx = _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=None))

    @tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        raise ToolInputError("stub_file must point to a .pyi file")

    with pytest.raises(ToolError) as raised:
        await tool(ctx, file_path=str(root / "mod.py"))

    assert str(raised.value) == "[INVALID_INPUT] stub_file must point to a .pyi file"


@pytest.mark.asyncio
async def test_wrapper_leaves_unanticipated_exceptions_untranslated(tmp_path: Path) -> None:
    """Only ToolInputError and BackendError are translated; other exceptions stay opaque."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    ctx = _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=None))

    @tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        raise ValueError("internal invariant")

    with pytest.raises(ValueError, match="internal invariant"):
        await tool(ctx, file_path=str(root / "mod.py"))


# ── mixed-workspace requests (nested-workspace-multi-path-boundary) ─────


def _nested_layout(tmp_path: Path, nested_marker: str) -> tuple[Path, Path]:
    """Create an outer checkout and a nested project root, each with two modules."""
    outer = tmp_path / "outer"
    nested = outer / "packages" / "inner"
    nested.mkdir(parents=True)
    (outer / ".git").mkdir()
    if nested_marker == ".git":
        (nested / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    else:
        (nested / nested_marker).touch()
    for root in (outer, nested):
        (root / "a.py").touch()
        (root / "b.py").touch()
    return outer, nested


def _real_registry_ctx() -> tuple[SimpleNamespace, AsyncMock]:
    """Build a ctx over a real registry whose ``get_backends`` is a spy returning root-matched backends.

    Like the real ``get_backends``, the spy hands out the backends with one lease acquired;
    the boundary releases it through the registry.
    """
    registry = WorkspaceRegistry()

    async def _get_backends(path: str) -> WorkspaceBackends:
        backends = _backends(registry.resolve_workspace_root(Path(path)))
        backends.acquire()
        return backends

    spy = AsyncMock(side_effect=_get_backends)
    registry.get_backends = spy  # type: ignore[method-assign]
    return _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=None)), spy


_MIXED_ROOT_MESSAGE = r"^\[INVALID_INPUT\] Paths span multiple workspaces"


@pytest.mark.asyncio
@pytest.mark.parametrize("nested_marker", [".git", "pyproject.toml"])
@pytest.mark.parametrize("outer_first", [True, False])
@pytest.mark.parametrize("shape", ["file_paths", "move", "root_and_list", "steps"])
async def test_wrapper_rejects_mixed_workspace_paths_before_execution(
    tmp_path: Path,
    nested_marker: str,
    outer_first: bool,
    shape: str,
) -> None:
    """Explicit paths in different workspaces fail in either order; no backend starts, no tool runs."""
    outer, nested = _nested_layout(tmp_path, nested_marker)
    first, second = (outer, nested) if outer_first else (nested, outer)
    ctx, spy = _real_registry_ctx()
    called = False

    @tool_error_boundary
    async def tool(ctx: object, **kwargs: object) -> str:
        nonlocal called
        called = True
        return "ok"

    kwargs: dict[str, object]
    if shape == "file_paths":
        kwargs = {"file_paths": [str(first / "a.py"), str(second / "a.py")]}
    elif shape == "move":
        kwargs = {"source_file": str(first / "a.py"), "destination_file": str(second / "b.py")}
    elif shape == "root_and_list":
        kwargs = {"root_path": str(first), "file_paths": [str(second / "a.py")]}
    else:
        kwargs = {"steps": [_rename_step(str(first / "a.py")), _rename_step(str(second / "a.py"))]}

    with pytest.raises(ToolError, match=_MIXED_ROOT_MESSAGE):
        await tool(ctx, **kwargs)

    assert called is False
    spy.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("which", ["outer", "nested"])
@pytest.mark.parametrize("shape", ["file_paths", "move", "steps"])
async def test_wrapper_dispatches_same_workspace_multi_path(tmp_path: Path, which: str, shape: str) -> None:
    """Same-root file lists, moves and transactions still dispatch with that workspace's backends."""
    outer, nested = _nested_layout(tmp_path, ".git")
    root = outer if which == "outer" else nested
    ctx, spy = _real_registry_ctx()
    seen: list[Path] = []

    @tool_error_boundary
    async def tool(ctx: object, **kwargs: object) -> str:
        seen.append(get_current_backends().config.workspace_root)
        return "ok"

    if shape == "file_paths":
        kwargs: dict[str, object] = {"file_paths": [str(root / "a.py"), str(root / "b.py")]}
    elif shape == "move":
        kwargs = {"source_file": str(root / "a.py"), "destination_file": str(root / "b.py")}
    else:
        kwargs = {"steps": [_rename_step(str(root / "a.py")), _rename_step(str(root / "b.py"))]}

    assert await tool(ctx, **kwargs) == "ok"
    assert seen == [root.resolve()]
    spy.assert_awaited_once()


@pytest.mark.asyncio
async def test_wrapper_keeps_outside_workspace_error_for_unmarked_second_path(tmp_path: Path) -> None:
    """A later path under no known root or marker keeps the typed containment error."""
    outer, _nested = _nested_layout(tmp_path, ".git")
    unmarked = tmp_path / "unmarked"
    unmarked.mkdir()
    (unmarked / "x.py").touch()
    ctx, _spy = _real_registry_ctx()

    @tool_error_boundary
    async def tool(ctx: object, file_paths: list[str]) -> str:
        return "ok"

    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] File path is outside the workspace root"):
        await tool(ctx, file_paths=[str(outer / "a.py"), str(unmarked / "x.py")])


# ── nested edit paths (diff-preview-path-scope) ─────────────────────────


def _diff_preview_tool() -> Callable[..., Awaitable[Any]]:
    """Wrap ``diff_preview`` under the boundary exactly as its registration does."""
    (record,) = (record for record in TOOL_RECORDS if record.func is diff_preview)
    return tool_error_boundary(record.func, workspace=record.workspace)


def _edit(file_path: str) -> TextEdit:
    """Build a schema-validated one-character edit, as the SDK hands it to the boundary."""
    return TextEdit(
        file_path=file_path,
        range=Range(start=Position(line=0, character=0), end=Position(line=0, character=1)),
        new_text="Y",
    )


def _link_dir(link: Path, target: Path) -> None:
    """Make *link* a directory symlink to *target*; on Windows fall back to a junction."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            raise
    created = subprocess.run(  # noqa: S603 - fixed argv, test-owned paths
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],  # noqa: S607
        capture_output=True,
        check=False,
    )
    if created.returncode != 0:
        pytest.skip("neither a directory symlink nor a junction can be created here")


def _escape_layout(tmp_path: Path) -> tuple[Path, Path]:
    """Create a marked workspace with one module plus an unmarked sibling holding a secret."""
    workspace = tmp_path / "ws"
    (workspace / "sub").mkdir(parents=True)
    (workspace / ".git").mkdir()
    (workspace / "a.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("TOPSECRET\n", encoding="utf-8")
    return workspace, outside


def _forbid_disk_diff(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make any attempt to build a diff fail loudly; returns the (empty) list of paths it saw."""
    seen: list[str] = []

    def _fail(file_path: str, edits: object) -> str:
        seen.append(file_path)
        raise AssertionError(f"diff_preview reached the disk read for {file_path}")

    monkeypatch.setattr(composite, "build_unified_diff", _fail)
    return seen


@pytest.mark.asyncio
async def test_diff_preview_in_scope_preview_succeeds_with_resolved_paths(tmp_path: Path) -> None:
    """An in-scope preview still returns its diff and the edit path is the resolved one."""
    workspace, _outside = _escape_layout(tmp_path)
    ctx, spy = _real_registry_ctx()
    spelled = workspace / "sub" / ".." / "a.py"

    result = await _diff_preview_tool()(ctx, edits=[_edit(str(spelled))])

    assert len(result) == 1
    assert "-x = 1" in result[0].unified_diff
    assert result[0].file_path == str((workspace / "a.py").resolve())
    spy.assert_not_awaited()


class _BackendlessRegistry(WorkspaceRegistry):
    """A real registry that fails loudly if any workspace backend is initialized."""

    async def _initialize_workspace(self, root: Path) -> WorkspaceBackends:
        raise AssertionError(f"a workspace backend was initialized for {root}")


def _backendless_registry_ctx() -> tuple[SimpleNamespace, WorkspaceRegistry]:
    """Build a ctx over a registry that forbids backend initialization."""
    registry = _BackendlessRegistry()
    return _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=None)), registry


@pytest.mark.asyncio
async def test_diff_preview_without_edits_needs_no_workspace() -> None:
    """An empty edit list selects no workspace, so it returns no diffs instead of failing on missing backends."""
    ctx, registry = _backendless_registry_ctx()

    assert await _diff_preview_tool()(ctx, edits=[]) == []
    assert registry.active_backends() == []


@pytest.mark.asyncio
async def test_diff_preview_with_zero_live_backends_starts_none(tmp_path: Path) -> None:
    """An in-scope preview on a cold registry validates the path and diffs without starting a backend."""
    workspace, _outside = _escape_layout(tmp_path)
    ctx, registry = _backendless_registry_ctx()

    result = await _diff_preview_tool()(ctx, edits=[_edit(str(workspace / "a.py"))])

    assert "-x = 1" in result[0].unified_diff
    assert registry.active_backends() == []


@pytest.mark.asyncio
async def test_diff_preview_with_several_live_workspaces_touches_none(tmp_path: Path) -> None:
    """With two workspaces live, a preview scoped to one of them neither starts nor touches any backend."""
    workspace, _outside = _escape_layout(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    (other / ".git").mkdir()
    ctx, registry = _backendless_registry_ctx()
    live = {workspace.resolve(): _backends(workspace.resolve()), other.resolve(): _backends(other.resolve())}
    for backends in live.values():
        backends.last_accessed = 1.0
    registry._workspaces.update(live)

    result = await _diff_preview_tool()(ctx, edits=[_edit(str(workspace / "a.py"))])

    assert "-x = 1" in result[0].unified_diff
    assert set(registry._workspaces) == set(live)
    assert [backends.last_accessed for backends in live.values()] == [1.0, 1.0]


@pytest.mark.asyncio
@pytest.mark.parametrize("escape", ["outside", "dotdot", "file_link", "dir_link"])
async def test_diff_preview_rejects_edit_paths_leaving_the_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, escape: str
) -> None:
    """An outside, ``..``, symlinked-file or linked-directory edit path is rejected before any read."""
    workspace, outside = _escape_layout(tmp_path)
    secret = outside / "secret.txt"
    if escape == "outside":
        bad = secret
    elif escape == "dotdot":
        bad = workspace / "sub" / ".." / ".." / "outside" / "secret.txt"
    elif escape == "file_link":
        bad = workspace / "link.txt"
        try:
            os.symlink(secret, bad)
        except OSError:
            pytest.skip("file symlinks need a privilege this runner lacks")
    else:
        _link_dir(workspace / "jlink", outside)
        bad = workspace / "jlink" / "secret.txt"
    seen = _forbid_disk_diff(monkeypatch)
    ctx, _spy = _real_registry_ctx()
    registry = get_multi_context(ctx).registry

    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] File path is outside the workspace root"):
        await _diff_preview_tool()(ctx, edits=[_edit(str(workspace / "a.py")), _edit(str(bad))])

    assert seen == []
    assert registry.get_known_roots() == []
    assert registry._auto_roots == set()


@pytest.mark.asyncio
async def test_diff_preview_rejects_unmarked_first_edit_without_registering_a_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path under no marker or known root is rejected and leaves the registry's roots untouched."""
    _workspace, outside = _escape_layout(tmp_path)
    seen = _forbid_disk_diff(monkeypatch)
    ctx, spy = _real_registry_ctx()
    registry = get_multi_context(ctx).registry

    with pytest.raises(ToolError, match=r"^\[(INVALID_INPUT|WORKSPACE_RESOLUTION)\]"):
        await _diff_preview_tool()(ctx, edits=[_edit(str(outside / "secret.txt"))])

    assert seen == []
    assert registry._known_roots == []
    spy.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("nested_marker", [".git", "pyproject.toml"])
@pytest.mark.parametrize("outer_first", [True, False])
async def test_diff_preview_rejects_edits_spanning_nested_workspaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nested_marker: str, outer_first: bool
) -> None:
    """Edits in an enclosing checkout and a nested project are different workspaces in either order."""
    outer, nested = _nested_layout(tmp_path, nested_marker)
    first, second = (outer, nested) if outer_first else (nested, outer)
    seen = _forbid_disk_diff(monkeypatch)
    ctx, spy = _real_registry_ctx()
    registry = get_multi_context(ctx).registry

    with pytest.raises(ToolError, match=_MIXED_ROOT_MESSAGE):
        await _diff_preview_tool()(ctx, edits=[_edit(str(first / "a.py")), _edit(str(second / "a.py"))])

    assert seen == []
    spy.assert_not_awaited()
    assert registry.get_known_roots() == []
    assert registry._auto_roots == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("relative", ["rel.py", "~/rel.py"])
async def test_diff_preview_rejects_relative_edit_path_naming_the_edit(tmp_path: Path, relative: str) -> None:
    """A relative edit path is rejected before workspace resolution, located by edit index."""
    workspace, _outside = _escape_layout(tmp_path)
    ctx, spy = _real_registry_ctx()

    with pytest.raises(ToolError, match=r"is not an absolute path \(parameter: edits\[1\]\.file_path\)"):
        await _diff_preview_tool()(ctx, edits=[_edit(str(workspace / "a.py")), _edit(relative)])

    spy.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="drive and UNC spellings exist only on Windows")
@pytest.mark.parametrize("spelling", ["rooted_no_drive", "drive_relative"])
async def test_diff_preview_rejects_windows_non_absolute_edit_paths(tmp_path: Path, spelling: str) -> None:
    """``\\x.py`` and ``C:x.py`` are not absolute on Windows and anchor at the server cwd, so they are rejected."""
    ctx, spy = _real_registry_ctx()
    bad = "\\x.py" if spelling == "rooted_no_drive" else "C:x.py"

    with pytest.raises(ToolError, match=r"is not an absolute path \(parameter: edits\[0\]\.file_path\)"):
        await _diff_preview_tool()(ctx, edits=[_edit(bad)])

    spy.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="drive-letter casing and extended-length paths exist only on Windows")
async def test_diff_preview_windows_spellings_resolve_to_the_same_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lowercase-drive and ``\\\\?\\`` spellings of an in-scope file pass; the outside file is still rejected."""
    workspace, outside = _escape_layout(tmp_path)
    in_scope = str(workspace / "a.py")
    ctx, _spy = _real_registry_ctx()

    lowered = in_scope[0].lower() + in_scope[1:]
    result = await _diff_preview_tool()(ctx, edits=[_edit(lowered)])
    assert "-x = 1" in result[0].unified_diff
    result = await _diff_preview_tool()(ctx, edits=[_edit("\\\\?\\" + in_scope)])
    assert "-x = 1" in result[0].unified_diff

    seen = _forbid_disk_diff(monkeypatch)
    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] File path is outside the workspace root"):
        await _diff_preview_tool()(
            ctx, edits=[_edit(in_scope), _edit("\\\\?\\" + str(outside / "secret.txt"))]
        )
    assert seen == []


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="UNC paths exist only on Windows")
async def test_diff_preview_rejects_unc_edit_path_before_workspace_resolution() -> None:
    """A UNC edit path is absolute but never reaches workspace resolution: it is rejected as input first."""
    registry = MagicMock()
    registry.resolve_workspace_root = MagicMock(side_effect=AssertionError("resolution reached"))
    registry.get_backends = AsyncMock()
    ctx = _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=None))

    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] .*UNC or device-namespace path.*edits\[0\]\.file_path"):
        await _diff_preview_tool()(ctx, edits=[_edit("\\\\server\\share\\x.py")])

    registry.resolve_workspace_root.assert_not_called()
    registry.get_backends.assert_not_awaited()


_UNC_NEEDLE = "unc-srv"
_UNC_SPELLINGS = [
    "\\\\unc-srv\\share\\a.py",
    "//unc-srv/share/a.py",
    "\\\\?\\UNC\\unc-srv\\share\\a.py",
    "\\\\.\\pipe\\unc-srv",
]


def _forbid_unc_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any resolve/exists/is_dir/stat/realpath call whose path names the UNC host; others pass through.

    The match is on the argument: an unconditional spy would trip on pytest and asyncio internals.
    """

    def guard(real: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(target: Any, *args: Any, **kwargs: Any) -> Any:
            if _UNC_NEEDLE in str(target):
                raise AssertionError(f"filesystem access for {target}")
            return real(target, *args, **kwargs)

        return wrapper

    for owner, name in ((Path, "resolve"), (Path, "exists"), (Path, "is_dir"), (os, "stat"), (os.path, "realpath")):
        monkeypatch.setattr(owner, name, guard(getattr(owner, name)))


async def _echo_tool(ctx: Any, **kwargs: Any) -> dict[str, Any]:
    """Stand-in tool body: the boundary under test runs before it."""
    return kwargs


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="UNC paths exist only on Windows")
@pytest.mark.parametrize("spelling", _UNC_SPELLINGS)
@pytest.mark.parametrize("shape", ["file_path", "root_path", "destination_file", "file_paths", "output_dir"])
async def test_unc_and_device_paths_are_rejected_before_any_filesystem_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spelling: str, shape: str
) -> None:
    """Every path-bearing argument shape is classified before ``resolve()``, marker probes or the registry."""
    workspace, _outside = _escape_layout(tmp_path)
    good = str(workspace / "a.py")
    arguments: dict[str, Any] = {
        "file_path": {"file_path": spelling},
        "root_path": {"root_path": spelling},
        "destination_file": {"file_path": good, "destination_file": spelling},
        "file_paths": {"file_paths": [good, spelling]},
        "output_dir": {"file_path": good, "output_dir": spelling},
    }[shape]
    ctx, spy = _real_registry_ctx()
    _forbid_unc_io(monkeypatch)

    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] .*UNC or device-namespace path"):
        await tool_error_boundary(_echo_tool)(ctx, **arguments)

    # ``output_dir`` never selects a workspace, so its valid ``file_path`` legitimately resolves
    # backends; the UNC value is checked afterwards and must never be among the resolved paths.
    expected_resolved = [good] if shape == "output_dir" else []
    assert [call.args[0] for call in spy.await_args_list] == expected_resolved


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="UNC paths exist only on Windows")
async def test_unc_edit_in_a_later_position_is_rejected_before_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nested ``edits[1].file_path`` is rejected by index before any resolution."""
    workspace, _outside = _escape_layout(tmp_path)
    ctx, spy = _real_registry_ctx()
    _forbid_unc_io(monkeypatch)

    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] .*UNC or device-namespace path.*edits\[1\]\.file_path"):
        await _diff_preview_tool()(ctx, edits=[_edit(str(workspace / "a.py")), _edit(_UNC_SPELLINGS[0])])

    spy.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="UNC paths exist only on Windows")
@pytest.mark.parametrize("spelling", _UNC_SPELLINGS)
async def test_multi_project_rename_rejects_unc_additional_roots_before_any_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spelling: str
) -> None:
    """``additional_roots`` is uncontained by design but each entry feeds ``Project(root)``, so UNC is refused first."""
    workspace, _outside = _escape_layout(tmp_path)
    (record,) = (record for record in TOOL_RECORDS if record.func.__name__ == "multi_project_rename")
    ctx, spy = _real_registry_ctx()
    _forbid_unc_io(monkeypatch)

    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] .*UNC or device-namespace path.*additional_roots\[1\]"):
        await tool_error_boundary(record.func, workspace=record.workspace)(
            ctx,
            additional_roots=[str(tmp_path), spelling],
            file_path=str(workspace / "a.py"),
            line=0,
            character=0,
            new_name="renamed",
        )

    spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_symbol_anchor_paths_are_validated_like_edit_paths(tmp_path: Path) -> None:
    """``symbols[].file_path`` goes through the boundary: outside rejected, in-scope rewritten to resolved."""
    workspace, outside = _escape_layout(tmp_path)
    ctx, _spy = _real_registry_ctx()
    seen: list[str] = []

    @tool_error_boundary
    async def tool(ctx: object, symbols: list[SymbolAnchor]) -> str:
        seen.extend(anchor.file_path for anchor in symbols)
        return "ok"

    spelled = str(workspace / "sub" / ".." / "a.py")
    assert await tool(ctx, symbols=[SymbolAnchor(file_path=spelled, line=0, character=0)]) == "ok"
    assert seen == [str((workspace / "a.py").resolve())]

    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] File path is outside the workspace root"):
        await tool(
            ctx,
            symbols=[
                SymbolAnchor(file_path=str(workspace / "a.py"), line=0, character=0),
                SymbolAnchor(file_path=str(outside / "secret.txt"), line=0, character=0),
            ],
        )
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_stub_file_is_validated_against_the_workspace(tmp_path: Path) -> None:
    """``stub_file`` is a path parameter: outside and relative values are rejected, in-scope passes."""
    workspace, outside = _escape_layout(tmp_path)
    ctx, _spy = _real_registry_ctx()
    stub = workspace / "a.pyi"
    stub.write_text("x: int\n", encoding="utf-8")

    @tool_error_boundary
    async def tool(ctx: object, source_file: str, stub_file: str | None = None) -> str:
        return "ok"

    source = str(workspace / "a.py")
    assert await tool(ctx, source_file=source, stub_file=str(stub)) == "ok"
    with pytest.raises(ToolError, match=r"^\[INVALID_INPUT\] File path is outside the workspace root"):
        await tool(ctx, source_file=source, stub_file=str(outside / "secret.txt"))
    with pytest.raises(ToolError, match=r"is not an absolute path \(parameter: stub_file\)"):
        await tool(ctx, source_file=source, stub_file="a.pyi")


@pytest.mark.asyncio
async def test_nested_path_item_without_a_validated_model_is_a_wiring_defect(tmp_path: Path) -> None:
    """An ``edits`` item that is not a validated model raises instead of silently skipping its path."""
    workspace, _outside = _escape_layout(tmp_path)
    ctx, _spy = _real_registry_ctx()

    @tool_error_boundary
    async def tool(ctx: object, edits: list[object]) -> str:
        return "unreachable"

    with pytest.raises(TypeError, match=r"edits\[0\]"):
        await tool(ctx, edits=[{"file_path": str(workspace / "a.py")}])


# Top-level parameters that look like paths but are deliberately not boundary-validated here.
_PATH_LIKE_ALLOWLIST: dict[str, str] = {
    "additional_roots": "extra Rope roots by design (UNC-guarded); containment is row multi-project-rename-roots",
    "target_modules": "dict KEYS are paths, UNC-guarded and contained by RopeBackend._workspace_python_file",
}
_PATH_SUFFIXES = ("_file", "_path", "_dir", "_directory")


def _schema_path_property_names(
    schema: object, defs: dict[str, object], seen: frozenset[str] = frozenset()
) -> set[str]:
    """Collect every property name ending in a path suffix (or ``file_path``) anywhere under *schema*."""
    found: set[str] = set()
    if isinstance(schema, dict):
        ref = schema.get("$ref")
        if isinstance(ref, str) and ref not in seen:
            found |= _schema_path_property_names(defs.get(ref.rsplit("/", 1)[-1]), defs, seen | {ref})
        for name, child in (schema.get("properties") or {}).items():
            if name.endswith(_PATH_SUFFIXES):
                found.add(name)
            found |= _schema_path_property_names(child, defs, seen)
        for key, child in schema.items():
            if key not in {"properties", "$ref", "$defs"}:
                found |= _schema_path_property_names(child, defs, seen)
    elif isinstance(schema, list):
        for child in schema:
            found |= _schema_path_property_names(child, defs, seen)
    return found


@pytest.mark.asyncio
async def test_every_path_bearing_tool_param_is_covered_by_the_boundary() -> None:
    """Drift guard: path-like top-level params and path-bearing nested models are all boundary-validated."""
    covered = set(PATH_PARAMS) | set(DIR_PARAMS) | {"file_paths"}
    nested_covered = set(tool_runtime.NESTED_PATH_PARAMS) | {"steps"}
    uncovered_scalars: set[str] = set()
    uncovered_nested: set[str] = set()
    seen_allowlisted: set[str] = set()
    for profile in TOOL_PROFILES:
        mcp = MCPServer(
            f"path-param drift guard ({profile})",
            tools=build_tools(profile),
        )
        for tool in await mcp.list_tools():
            defs = tool.input_schema.get("$defs", {})
            for name, prop in tool.input_schema.get("properties", {}).items():
                if name in _PATH_LIKE_ALLOWLIST:
                    seen_allowlisted.add(name)
                    continue
                if name.endswith(_PATH_SUFFIXES) and name not in covered:
                    uncovered_scalars.add(name)
                if _schema_path_property_names(prop, defs) and name not in covered | nested_covered:
                    uncovered_nested.add(name)
    assert not uncovered_scalars, f"path-like params missing from the boundary tables: {sorted(uncovered_scalars)}"
    assert not uncovered_nested, (
        f"path-bearing nested params missing from NESTED_PATH_PARAMS: {sorted(uncovered_nested)}"
    )
    assert seen_allowlisted == set(_PATH_LIKE_ALLOWLIST), "stale allowlist entry: no live tool takes it"


def _string_leaves(schema: object, defs: dict[str, object], leaf: str, seen: frozenset[str] = frozenset()) -> set[str]:
    """Return the label of every free-form string value reachable under *schema*.

    A label is the nearest property name; a dict key is ``<key>``, a dict value's own strings
    are labelled by the enclosing name. Enum and const strings are not free-form and are skipped.
    """
    found: set[str] = set()
    if not isinstance(schema, dict):
        return found
    ref = schema.get("$ref")
    if isinstance(ref, str):
        if ref in seen:
            return found
        return _string_leaves(defs.get(ref.rsplit("/", 1)[-1]), defs, leaf, seen | {ref})
    kind = schema.get("type")
    kinds = kind if isinstance(kind, list) else [kind]
    if "string" in kinds and "enum" not in schema and "const" not in schema:
        found.add(leaf)
    for name, child in (schema.get("properties") or {}).items():
        found |= _string_leaves(child, defs, name, seen)
    extra = schema.get("additionalProperties")
    if extra not in (None, False) or schema.get("propertyNames") or schema.get("patternProperties"):
        found.add("<key>")
        found |= _string_leaves(extra, defs, leaf, seen)
    found |= _string_leaves(schema.get("items"), defs, leaf, seen)
    for key in ("anyOf", "oneOf", "allOf", "prefixItems"):
        for child in schema.get(key) or []:
            found |= _string_leaves(child, defs, leaf, seen)
    return found


# String parameters that are not paths, as (parameter, label): each is text, a name or a pattern that no
# tool resolves against the filesystem. Every entry must be taken by a live tool (stale entries fail).
_NON_PATH_PARAMS: dict[tuple[str, str], str] = {
    ("action_title", "action_title"): "code action title matched against Pyright's offered actions",
    ("checks", "<key>"): "rope restructure check names",
    ("checks", "checks"): "rope restructure check expressions",
    ("default_value", "default_value"): "Python expression text inserted as a default",
    ("exclude_patterns", "exclude_patterns"): "regular expressions applied to already-validated file paths",
    ("goal", "goal"): "rope restructure goal pattern",
    ("imports", "imports"): "import statements for restructure",
    ("kind_filter", "kind_filter"): "symbol kind names",
    ("kinds", "kinds"): "symbol kind names",
    ("layers", "layers"): "dotted module-name prefixes compared with import names",
    ("name", "name"): "autoimport symbol name",
    ("name_pattern", "name_pattern"): "symbol-name pattern",
    ("operations", "default"): "change_signature default expression text",
    ("operations", "name"): "change_signature parameter name",
    ("operations", "new_name"): "change_signature parameter name (validate_identifier in the backend)",
    ("package_name", "package_name"): "dotted import name; every segment passes validate_identifier",
    ("pattern", "pattern"): "search or restructure pattern text",
    ("query", "query"): "symbol search text",
    ("replacement", "replacement"): "replacement pattern text",
    ("source", "source"): "in-memory source text, never a path",
    ("suppress_codes", "suppress_codes"): "diagnostic rule codes",
    ("symbol", "symbol"): "symbol name",
    ("target_modules", "target_modules"): "dict VALUES: symbol names moved into the keyed module",
    ("typed_dict_name", "typed_dict_name"): "generated class name",
}
# String values nested inside the path-bearing models (``edits``, ``symbols``, ``steps``) that are not paths.
_NESTED_NON_PATH_LEAVES: dict[str, str] = {
    "new_text": "replacement text of a TextEdit",
}
# Path strings the boundary does not see, each guarded at the sink that consumes it.
_SINK_GUARDED: dict[tuple[str, str], tuple[Callable[..., Any], str]] = {
    ("target_modules", "<key>"): (RopeBackend._workspace_python_file, "split_module target module keys"),
}


@pytest.mark.asyncio
async def test_every_string_parameter_is_classified_as_path_guarded_or_non_path() -> None:
    """Class guard, derived from the live schemas of every profile.

    Walks every parameter of every tool (nested objects, dict keys, list items) and requires each
    free-form string to be a boundary path/identifier parameter, in ``_LOCAL_ONLY_LIST_PARAMS``,
    guarded at a named sink that calls the UNC guard, or a documented non-path. A new tool or
    parameter with no classification fails here, so a path cannot reach I/O unguarded by omission.
    """
    boundary_scalars = set(PATH_PARAMS) | set(DIR_PARAMS)
    boundary_lists = set(tool_runtime._LIST_PATH_PARAMS) | set(tool_runtime._LOCAL_ONLY_LIST_PARAMS)
    nested = set(tool_runtime.NESTED_PATH_PARAMS) | {"steps"}
    identifiers = set(tool_runtime.IDENTIFIER_PARAMS) | set(tool_runtime._LIST_IDENTIFIER_PARAMS)
    unclassified: set[tuple[str, str]] = set()
    seen_non_path: set[tuple[str, str]] = set()
    seen_nested_non_path: set[str] = set()
    seen_sinks: set[tuple[str, str]] = set()
    for profile in TOOL_PROFILES:
        mcp = MCPServer(f"string parameter classification ({profile})", tools=build_tools(profile))
        for tool in await mcp.list_tools():
            defs = tool.input_schema.get("$defs", {})
            for top, prop in tool.input_schema.get("properties", {}).items():
                for leaf in _string_leaves(prop, defs, top):
                    if top in boundary_scalars | boundary_lists | identifiers and leaf == top:
                        continue
                    if top in nested:
                        if leaf == "file_path" or leaf in identifiers:
                            continue
                        if leaf in _NESTED_NON_PATH_LEAVES:
                            seen_nested_non_path.add(leaf)
                            continue
                    elif (top, leaf) in _SINK_GUARDED:
                        seen_sinks.add((top, leaf))
                        continue
                    elif (top, leaf) in _NON_PATH_PARAMS:
                        seen_non_path.add((top, leaf))
                        continue
                    unclassified.add((top, leaf))
    assert not unclassified, f"unclassified string parameters (classify each): {sorted(unclassified)}"
    assert seen_non_path == set(_NON_PATH_PARAMS), "stale _NON_PATH_PARAMS entry"
    assert seen_nested_non_path == set(_NESTED_NON_PATH_LEAVES), "stale _NESTED_NON_PATH_LEAVES entry"
    assert seen_sinks == set(_SINK_GUARDED), "stale _SINK_GUARDED entry"
    for (top, _leaf), (sink, _what) in _SINK_GUARDED.items():
        assert "require_local_path(" in inspect.getsource(sink), f"sink for {top} does not call the UNC guard"


def test_validate_params_rejects_non_nfkc_identifiers(tmp_path: Path) -> None:
    """Identifier parameters must be NFKC-normal: ``ast`` normalises names, so ﬁle would alias file unseen."""
    with pytest.raises(ValueError, match="not NFKC-normalized"):
        _validate_params({"new_name": "ﬁle"}, tmp_path)
    with pytest.raises(ValueError, match="not NFKC-normalized"):
        _validate_params({"class_names": ["Good", "ﬁle"]}, tmp_path)
    with pytest.raises(ValueError, match="not NFKC-normalized"):
        _validate_params({"steps": [_rename_step(str(tmp_path / "a.py"), new_name="ﬁle")]}, tmp_path)


# ── root_path selection (bl-0056) ────────────────────────────────────────


def _patched_backend_classes() -> contextlib.ExitStack:
    """Patch the registry's backend constructors so a real ``WorkspaceRegistry`` starts mocks only."""
    stack = contextlib.ExitStack()
    stack.enter_context(
        patch(
            "python_refactor_mcp.workspace_registry.discover_config",
            side_effect=lambda root: SimpleNamespace(workspace_root=root),
        )
    )
    stack.enter_context(
        patch("python_refactor_mcp.workspace_registry.PyrightLSPClient", side_effect=lambda _c: AsyncMock())
    )
    stack.enter_context(patch("python_refactor_mcp.workspace_registry.JediBackend"))
    stack.enter_context(patch("python_refactor_mcp.workspace_registry.RopeBackend"))
    return stack


@pytest.mark.asyncio
async def test_root_path_selects_an_unregistered_repo_root_in_a_real_registry(tmp_path: Path) -> None:
    """A path-less tool with ``root_path`` selects that repo root and marks it selected."""
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / ".git").mkdir()
    registry = WorkspaceRegistry()
    ctx = _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=None))
    seen: list[WorkspaceBackends] = []

    @tool_error_boundary
    async def search_like(ctx: object, root_path: str | None = None) -> str:
        seen.append(get_current_backends())
        return "ok"

    with _patched_backend_classes():
        assert await search_like(ctx, root_path=str(repo)) == "ok"
        assert await search_like(ctx) == "ok"

    assert [backends.config.workspace_root for backends in seen] == [repo.resolve(), repo.resolve()]
    assert seen[0] is seen[1]
    assert seen[0].selected is True


@pytest.mark.asyncio
async def test_root_path_selects_a_worktree_root_inside_a_known_primary(tmp_path: Path) -> None:
    """With the primary checkout known, ``root_path=<primary>/.worktrees/x`` selects the worktree (ADR 0002)."""
    primary = (tmp_path / "primary").resolve()
    worktree = primary / ".worktrees" / "x"
    worktree.mkdir(parents=True)
    (primary / ".git").mkdir()
    (worktree / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    registry = WorkspaceRegistry()
    await registry.set_roots([primary])
    ctx = _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=primary))

    @tool_error_boundary
    async def search_like(ctx: object, root_path: str | None = None) -> Path:
        return get_current_backends().config.workspace_root

    with _patched_backend_classes():
        assert await search_like(ctx, root_path=str(worktree)) == worktree


@pytest.mark.asyncio
async def test_root_path_with_a_file_path_in_another_workspace_keeps_the_multi_workspace_error(
    tmp_path: Path,
) -> None:
    """``root_path`` is one more selector: a conflicting ``file_path`` is rejected before any backend starts."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        root.mkdir()
        (root / ".git").mkdir()
        (root / "a.py").touch()
    ctx = _ctx_with(MultiWorkspaceContext(registry=_BackendlessRegistry(), cli_workspace_root=None))

    @tool_error_boundary
    async def tool(ctx: object, root_path: str | None = None, file_path: str | None = None) -> str:
        raise AssertionError("tool body must not run")

    with pytest.raises(ToolError, match=_MIXED_ROOT_MESSAGE):
        await tool(ctx, root_path=str(first), file_path=str(second / "a.py"))


@pytest.mark.asyncio
async def test_relative_root_path_is_rejected_before_any_backend_starts(tmp_path: Path) -> None:
    """A relative ``root_path`` cannot select (or start) a workspace through the server cwd."""
    ctx = _ctx_with(MultiWorkspaceContext(registry=_BackendlessRegistry(), cli_workspace_root=None))

    @tool_error_boundary
    async def tool(ctx: object, root_path: str | None = None) -> str:
        raise AssertionError("tool body must not run")

    with pytest.raises(ToolError, match=r"is not an absolute path \(parameter: root_path\)"):
        await tool(ctx, root_path="some/dir")


@pytest.mark.asyncio
async def test_root_only_path_bearing_call_does_not_select_the_workspace(tmp_path: Path) -> None:
    """A diff_preview call resolves a root only: it must not make a pre-warmed workspace look selected."""
    workspace, _outside = _escape_layout(tmp_path)
    registry = _BackendlessRegistry()
    warmed = _backends(workspace.resolve())
    warmed.selected = False
    registry._workspaces[workspace.resolve()] = warmed
    ctx = _ctx_with(MultiWorkspaceContext(registry=registry, cli_workspace_root=workspace.resolve()))

    result = await _diff_preview_tool()(ctx, edits=[_edit(str(workspace / "a.py"))])

    assert "-x = 1" in result[0].unified_diff
    assert warmed.selected is False
    with pytest.raises(AmbiguousWorkspaceError, match="pre-warmed, not selected"):
        registry.implicit_workspace()
