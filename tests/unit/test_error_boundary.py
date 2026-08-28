"""Unit tests for the _tool_error_boundary wrapper and its extracted helpers.

These pin the observable behavior of the error boundary so the
``_resolve_backends`` / ``_validate_params`` decomposition stays a pure
refactor: backend resolution, the per-call ContextVar, path + identifier
validation, timing instrumentation, and ``BackendError`` -> ``ValueError``
translation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.server import (
    MultiWorkspaceContext,
    _get_current_backends,
    _resolve_backends,
    _tool_error_boundary,
    _validate_params,
)
from python_refactor_mcp.workspace_registry import WorkspaceBackends


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
        {"steps": [{"tool": "rename_symbol", "args": {"file_path": str(target)}}]},
    )

    assert resolved is backends
    registry.get_backends.assert_awaited_once_with(str(target))


@pytest.mark.asyncio
async def test_resolve_backends_no_path_uses_most_recent(tmp_path: Path) -> None:
    """No path params -> registry.get_most_recent() supplies the fallback."""
    backends = _backends(tmp_path / "ws")
    registry = MagicMock()
    registry.get_most_recent = MagicMock(return_value=backends)
    registry.get_backends = AsyncMock()
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    ctx = _ctx_with(multi_ctx)

    resolved = await _resolve_backends(ctx, {"limit": 5})

    assert resolved is backends
    registry.get_most_recent.assert_called_once()
    registry.get_backends.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_backends_cli_fallback_when_no_recent(tmp_path: Path) -> None:
    """No path + empty registry -> the CLI workspace __fallback__ path is used."""
    cli_root = tmp_path / "cli"
    backends = _backends(cli_root)
    registry = MagicMock()
    registry.get_most_recent = MagicMock(return_value=None)
    registry.get_backends = AsyncMock(return_value=backends)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=cli_root)
    ctx = _ctx_with(multi_ctx)

    resolved = await _resolve_backends(ctx, {})

    assert resolved is backends
    registry.get_backends.assert_awaited_once_with(str(cli_root / "__fallback__"))


@pytest.mark.asyncio
async def test_resolve_backends_none_when_no_multi_ctx() -> None:
    """A ctx without a MultiWorkspaceContext lifespan payload resolves to None."""
    ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=object(), session=MagicMock()))

    resolved = await _resolve_backends(ctx, {"file_path": "/somewhere/mod.py"})

    assert resolved is None


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


def test_validate_params_resolves_nested_transaction_paths(tmp_path: Path) -> None:
    """Every transaction step path is normalized against the selected workspace."""
    kwargs = {
        "steps": [
            {"tool": "rename_symbol", "args": {"file_path": str(tmp_path / "a.py")}},
            {"tool": "rename_symbol", "args": {"file_path": str(tmp_path / "b.py")}},
        ]
    }

    _validate_params(kwargs, tmp_path)

    assert [step["args"]["file_path"] for step in kwargs["steps"]] == [
        str((tmp_path / "a.py").resolve()),
        str((tmp_path / "b.py").resolve()),
    ]


def test_validate_params_rejects_bad_identifier(tmp_path: Path) -> None:
    """An invalid identifier parameter raises ValueError."""
    with pytest.raises(ValueError, match="not a valid Python identifier"):
        _validate_params({"new_name": "1bad"}, tmp_path)


def test_validate_params_accepts_valid_identifier(tmp_path: Path) -> None:
    """A valid identifier passes through untouched."""
    kwargs = {"new_name": "good_name"}
    _validate_params(kwargs, tmp_path)
    assert kwargs["new_name"] == "good_name"


# ── _tool_error_boundary (wrapper integration) ───────────────────────────


@pytest.mark.asyncio
async def test_wrapper_translates_backend_error(tmp_path: Path) -> None:
    """BackendError raised by the wrapped fn surfaces as ValueError."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    ctx = _ctx_with(multi_ctx)

    @_tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        raise BackendError("backend boom")

    with pytest.raises(ValueError, match="backend boom"):
        await tool(ctx, file_path=str(root / "mod.py"))


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

    @_tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        seen["backends"] = _get_current_backends()
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

    @_tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        return "ok"

    await tool(ctx, file_path=str(root / "mod.py"))

    with pytest.raises(RuntimeError, match="No workspace backends available"):
        _get_current_backends()


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

    @_tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        nonlocal called
        called = True
        return "ok"

    # get_backends returns the ws-rooted backends, but the path is elsewhere.
    with pytest.raises(ValueError, match="outside the workspace root"):
        await tool(ctx, file_path=str(tmp_path / "elsewhere" / "mod.py"))
    assert called is False


@pytest.mark.asyncio
async def test_wrapper_records_timing_via_server_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The wrapper emits timing through standard server logging."""
    root = tmp_path / "ws"
    backends = _backends(root)
    registry = MagicMock()
    registry.get_backends = AsyncMock(return_value=backends)
    multi_ctx = MultiWorkspaceContext(registry=registry, cli_workspace_root=None)
    ctx = _ctx_with(multi_ctx)

    @_tool_error_boundary
    async def tool(ctx: object, file_path: str) -> str:
        return "ok"

    with caplog.at_level(logging.DEBUG, logger="python_refactor_mcp.server"):
        await tool(ctx, file_path=str(root / "mod.py"))

    assert "tool completed in" in caplog.text


@pytest.mark.asyncio
async def test_wrapper_validates_identifier_without_backends() -> None:
    """Identifier validation runs even when no backends resolve (ctx is None)."""

    @_tool_error_boundary
    async def tool(new_name: str) -> str:
        return "ok"

    # No ctx -> backends is None, but identifier validation still applies.
    with pytest.raises(ValueError, match="not a valid Python identifier"):
        await tool(new_name="1bad")
