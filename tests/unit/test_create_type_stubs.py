"""Unit tests for ``create_type_stubs`` (Pyright CLI subprocess mocked)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import PyrightError, ToolInputError
from python_refactor_mcp.tools.analysis import type_stubs
from python_refactor_mcp.tools.analysis.type_stubs import create_type_stubs


def _config(workspace: Path) -> ServerConfig:
    return ServerConfig(
        workspace_root=workspace,
        python_executable=workspace / "python.exe",
        venv_path=None,
        pyright_executable="pyright-langserver",
        pyrightconfig_path=None,
        rope_prefs={},
    )


class _FakeCli:
    """Records createstub invocations and simulates Pyright's typings/ output in cwd."""

    def __init__(self, returncode: int = 0, output: str = "", stub_files: tuple[str, ...] = ()) -> None:
        self.returncode = returncode
        self.output = output
        self.stub_files = stub_files
        self.calls: list[tuple[str, Path]] = []

    async def __call__(self, config: ServerConfig, package_name: str, cwd: Path) -> tuple[int, str]:
        self.calls.append((package_name, cwd))
        for relative in self.stub_files:
            path = cwd / "typings" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def f() -> None: ...\n", encoding="utf-8")
        return self.returncode, self.output


@pytest.fixture
def fake_cli(monkeypatch: pytest.MonkeyPatch) -> _FakeCli:
    cli = _FakeCli(output="Type stub was created for 'pkg'", stub_files=("pkg/__init__.pyi", "pkg/sub/mod.pyi"))
    monkeypatch.setattr(type_stubs, "_run_pyright_createstub", cli)
    return cli


@pytest.mark.asyncio
async def test_happy_path_moves_stubs_to_default_typings_root(tmp_path: Path, fake_cli: _FakeCli) -> None:
    result = await create_type_stubs(_config(tmp_path), "pkg")

    stub_root = tmp_path / "typings"
    assert result.package_name == "pkg"
    assert Path(result.output_dir) == stub_root.resolve()
    assert [Path(item) for item in result.files] == [
        (stub_root / "pkg" / "__init__.pyi").resolve(),
        (stub_root / "pkg" / "sub" / "mod.pyi").resolve(),
    ]
    assert all(Path(item).is_file() for item in result.files)
    assert fake_cli.calls[0][0] == "pkg"
    # The CLI ran in a scratch directory, never the workspace.
    assert fake_cli.calls[0][1] != tmp_path


@pytest.mark.asyncio
async def test_relative_output_dir_anchors_at_workspace(tmp_path: Path, fake_cli: _FakeCli) -> None:
    result = await create_type_stubs(_config(tmp_path), "pkg.sub", output_dir="stubs")

    assert Path(result.output_dir) == (tmp_path / "stubs").resolve()
    assert (tmp_path / "stubs" / "pkg" / "sub" / "mod.pyi").is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", "not an identifier!!", "pkg..sub", "class", "1pkg"])
async def test_rejects_invalid_package_name(tmp_path: Path, fake_cli: _FakeCli, name: str) -> None:
    with pytest.raises(ToolInputError, match="package_name"):
        await create_type_stubs(_config(tmp_path), name)
    assert fake_cli.calls == []


@pytest.mark.asyncio
async def test_rejects_output_dir_outside_workspace(tmp_path: Path, fake_cli: _FakeCli) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    with pytest.raises(ToolInputError, match="outside the workspace root"):
        await create_type_stubs(_config(workspace), "pkg", output_dir=str(tmp_path / "elsewhere"))
    with pytest.raises(ToolInputError, match="outside the workspace root"):
        await create_type_stubs(_config(workspace), "pkg", output_dir="../elsewhere")
    assert fake_cli.calls == []


@pytest.mark.asyncio
async def test_refuses_existing_target(tmp_path: Path, fake_cli: _FakeCli) -> None:
    existing = tmp_path / "typings" / "pkg"
    existing.mkdir(parents=True)
    with pytest.raises(ToolInputError, match="already exists"):
        await create_type_stubs(_config(tmp_path), "pkg")
    assert fake_cli.calls == []
    assert list(existing.iterdir()) == []


@pytest.mark.asyncio
async def test_unresolved_import_is_caller_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli = _FakeCli(
        returncode=2,
        output="Error occurred when creating type stub: Import 'nopkg' could not be resolved",
    )
    monkeypatch.setattr(type_stubs, "_run_pyright_createstub", cli)
    with pytest.raises(ToolInputError, match="Import 'nopkg' could not be resolved"):
        await create_type_stubs(_config(tmp_path), "nopkg")
    assert not (tmp_path / "typings").exists()


@pytest.mark.asyncio
async def test_other_nonzero_exit_is_backend_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(type_stubs, "_run_pyright_createstub", _FakeCli(returncode=1, output="node crashed"))
    with pytest.raises(PyrightError, match="node crashed"):
        await create_type_stubs(_config(tmp_path), "pkg")


@pytest.mark.asyncio
async def test_exit_zero_without_stubs_is_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(type_stubs, "_run_pyright_createstub", _FakeCli(output="Type stub was created"))
    with pytest.raises(ToolInputError, match=r"no \.pyi stubs"):
        await create_type_stubs(_config(tmp_path), "pkg")
    assert not (tmp_path / "typings" / "pkg").exists()


class _HungProcess:
    """Fake asyncio subprocess whose ``communicate()`` never completes."""

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.communicate_cancelled = False
        self.kill_calls = 0
        self.wait_awaited = False

    async def communicate(self) -> tuple[bytes, bytes]:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.communicate_cancelled = True
            raise
        raise AssertionError("unreachable: communicate() must hang until cancelled")

    def kill(self) -> None:
        self.kill_calls += 1

    async def wait(self) -> int:
        # Reaping must follow the kill, never precede it.
        assert self.kill_calls == 1
        self.wait_awaited = True
        self.returncode = -9
        return self.returncode


@pytest.mark.asyncio
async def test_createstub_timeout_kills_and_reaps_hung_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    process = _HungProcess()
    spawned: list[tuple[Any, ...]] = []

    async def fake_exec(*args: Any, **kwargs: Any) -> _HungProcess:
        spawned.append(args)
        return process

    monkeypatch.setattr(type_stubs, "_CREATESTUB_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    with pytest.raises(PyrightError, match=r"timed out after .* for 'pkg'"):
        await asyncio.wait_for(create_type_stubs(_config(tmp_path), "pkg"), timeout=5)

    assert len(spawned) == 1
    assert "--createstub" in spawned[0]
    assert process.communicate_cancelled
    assert process.kill_calls == 1
    assert process.wait_awaited
    assert not (tmp_path / "typings").exists()
