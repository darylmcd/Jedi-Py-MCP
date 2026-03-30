"""Unit tests for WorkspaceRegistry multi-workspace management."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from python_refactor_mcp.errors import WorkspaceResolutionError
from python_refactor_mcp.workspace_registry import WorkspaceBackends, WorkspaceRegistry


def _mock_config(root: Path) -> MagicMock:
    """Create a mock ServerConfig with workspace_root set."""
    config = MagicMock()
    config.workspace_root = root
    return config


def _mock_backends(root: Path) -> WorkspaceBackends:
    """Create a WorkspaceBackends with mocked backend instances."""
    config = _mock_config(root)
    pyright = AsyncMock()
    jedi = MagicMock()
    rope = MagicMock()
    return WorkspaceBackends(config=config, pyright=pyright, jedi=jedi, rope=rope)


# ── WorkspaceBackends lifecycle ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_starts_all_backends() -> None:
    backends = _mock_backends(Path("/project"))
    await backends.initialize()

    backends.pyright.start.assert_awaited_once()
    backends.jedi.initialize.assert_called_once()
    backends.rope.initialize.assert_called_once()
    assert backends._initialized is True


@pytest.mark.asyncio
async def test_initialize_is_idempotent() -> None:
    backends = _mock_backends(Path("/project"))
    await backends.initialize()
    await backends.initialize()

    backends.pyright.start.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_stops_backends() -> None:
    backends = _mock_backends(Path("/project"))
    await backends.initialize()
    await backends.shutdown()

    backends.pyright.shutdown.assert_awaited_once()
    backends.rope.close.assert_called_once()
    assert backends._initialized is False


@pytest.mark.asyncio
async def test_shutdown_without_init_is_noop() -> None:
    backends = _mock_backends(Path("/project"))
    await backends.shutdown()

    backends.pyright.shutdown.assert_not_awaited()


def test_touch_updates_timestamp() -> None:
    backends = _mock_backends(Path("/project"))
    old = backends.last_accessed
    backends.touch()
    assert backends.last_accessed >= old


# ── WorkspaceRegistry resolution ─────────────────────────────────────────


def test_resolve_known_root(tmp_path: Path) -> None:
    registry = WorkspaceRegistry()
    root = tmp_path / "project"
    root.mkdir()
    registry._known_roots = [root]

    result = registry.resolve_workspace_root(root / "src" / "main.py")
    assert result == root


def test_resolve_longest_prefix_match(tmp_path: Path) -> None:
    outer = tmp_path / "mono"
    inner = tmp_path / "mono" / "packages" / "core"
    outer.mkdir(parents=True)
    inner.mkdir(parents=True)

    registry = WorkspaceRegistry()
    registry._known_roots = [outer, inner]

    result = registry.resolve_workspace_root(inner / "src" / "main.py")
    assert result == inner


def test_resolve_walks_parents_for_markers(tmp_path: Path) -> None:
    project_root = tmp_path / "my_project"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname='test'\n")
    nested_file = project_root / "src" / "deep" / "module.py"
    nested_file.parent.mkdir(parents=True)
    nested_file.touch()

    registry = WorkspaceRegistry()
    result = registry.resolve_workspace_root(nested_file)

    assert result == project_root
    assert project_root in registry._known_roots


def test_resolve_walks_parents_for_git(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / ".git").mkdir()
    nested_file = project_root / "src" / "main.py"
    nested_file.parent.mkdir(parents=True)
    nested_file.touch()

    registry = WorkspaceRegistry()
    result = registry.resolve_workspace_root(nested_file)
    assert result == project_root


def test_resolve_raises_when_no_root_found(tmp_path: Path) -> None:
    registry = WorkspaceRegistry()
    # tmp_path has no project markers and is not a known root
    orphan = tmp_path / "orphan.py"
    orphan.touch()

    with pytest.raises(WorkspaceResolutionError, match="Cannot determine workspace root"):
        registry.resolve_workspace_root(orphan)


# ── WorkspaceRegistry get_backends ───────────────────────────────────────


@pytest.mark.asyncio
async def test_get_backends_creates_and_caches(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='test'\n")
    src = project / "main.py"
    src.write_text("x = 1\n")

    registry = WorkspaceRegistry()

    with patch("python_refactor_mcp.workspace_registry.discover_config") as mock_config, \
         patch("python_refactor_mcp.workspace_registry.PyrightLSPClient") as mock_pyright, \
         patch("python_refactor_mcp.workspace_registry.JediBackend"), \
         patch("python_refactor_mcp.workspace_registry.RopeBackend"):
        mock_config.return_value = _mock_config(project)
        mock_pyright_inst = AsyncMock()
        mock_pyright.return_value = mock_pyright_inst

        backends1 = await registry.get_backends(str(src))
        backends2 = await registry.get_backends(str(src))

    assert backends1 is backends2
    mock_config.assert_called_once()


# ── WorkspaceRegistry set_roots ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_roots_shuts_down_removed() -> None:
    registry = WorkspaceRegistry()
    root_a = Path("/a").resolve()
    root_b = Path("/b").resolve()

    backends_a = _mock_backends(root_a)
    backends_a._initialized = True
    registry._workspaces[root_a] = backends_a
    registry._known_roots = [root_a, root_b]

    await registry.set_roots([root_b])

    assert root_a not in registry._workspaces
    backends_a.pyright.shutdown.assert_awaited_once()


# ── WorkspaceRegistry eviction ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_evict_lru_removes_oldest(tmp_path: Path) -> None:
    registry = WorkspaceRegistry(max_workspaces=2)

    root_a = Path("/a").resolve()
    root_b = Path("/b").resolve()

    backends_a = _mock_backends(root_a)
    backends_a._initialized = True
    backends_a.last_accessed = 1.0

    backends_b = _mock_backends(root_b)
    backends_b._initialized = True
    backends_b.last_accessed = 2.0

    registry._workspaces = {root_a: backends_a, root_b: backends_b}

    await registry._evict_lru()

    assert root_a not in registry._workspaces
    assert root_b in registry._workspaces
    backends_a.pyright.shutdown.assert_awaited_once()


# ── WorkspaceRegistry shutdown_all ───────────────────────────────────────


@pytest.mark.asyncio
async def test_shutdown_all() -> None:
    registry = WorkspaceRegistry()

    backends_a = _mock_backends(Path("/a"))
    backends_a._initialized = True
    backends_b = _mock_backends(Path("/b"))
    backends_b._initialized = True

    registry._workspaces = {Path("/a"): backends_a, Path("/b"): backends_b}
    registry._known_roots = [Path("/a"), Path("/b")]

    await registry.shutdown_all()

    assert len(registry._workspaces) == 0
    assert len(registry._known_roots) == 0
    backends_a.pyright.shutdown.assert_awaited_once()
    backends_b.pyright.shutdown.assert_awaited_once()


# ── WorkspaceRegistry get_most_recent ────────────────────────────────────


def test_get_most_recent_returns_none_when_empty() -> None:
    registry = WorkspaceRegistry()
    assert registry.get_most_recent() is None


def test_get_most_recent_returns_latest() -> None:
    registry = WorkspaceRegistry()
    old = _mock_backends(Path("/old"))
    old.last_accessed = 1.0
    new = _mock_backends(Path("/new"))
    new.last_accessed = 2.0
    registry._workspaces = {Path("/old"): old, Path("/new"): new}

    assert registry.get_most_recent() is new


# ── Constructor validation ───────────────────────────────────────────────


def test_max_workspaces_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_workspaces must be >= 1"):
        WorkspaceRegistry(max_workspaces=0)
