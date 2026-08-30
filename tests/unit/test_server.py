"""Unit tests for server shell behavior."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from python_refactor_mcp import server
from python_refactor_mcp.config import DEFAULT_TOOL_PROFILE
from python_refactor_mcp.tool_registry import MAX_TOOLS_PER_PROFILE

# Shared 0-based position convention sentence. Every position-based tool
# description must embed this verbatim; this constant is the single source of
# truth the gate below asserts against. Keep it in sync with the wording in
# ``python_refactor_mcp.models.Position`` ("0-based line and character offset").
POSITION_CONVENTION_PHRASE = "Positions are 0-based (line and character offsets, LSP convention)."


def _production_import_graph() -> dict[str, set[str]]:
    """Build the package's module-level import graph from production sources."""
    package_root = Path(__file__).resolve().parents[2] / "src" / "python_refactor_mcp"
    modules: dict[str, Path] = {}
    for path in package_root.rglob("*.py"):
        relative_parts = list(path.relative_to(package_root).with_suffix("").parts)
        if relative_parts[-1] == "__init__":
            relative_parts.pop()
        suffix = f".{'.'.join(relative_parts)}" if relative_parts else ""
        modules[f"python_refactor_mcp{suffix}"] = path

    def known_module(target: str) -> str | None:
        candidates = [name for name in modules if target == name or target.startswith(f"{name}.")]
        return max(candidates, key=len) if candidates else None

    graph = {name: set() for name in modules}
    for source, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        current_package = source if path.name == "__init__.py" else source.rpartition(".")[0]
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    package_parts = current_package.split(".")
                    retained = package_parts[: len(package_parts) - (node.level - 1)]
                    base = ".".join((*retained, *(node.module or "").split("."))).rstrip(".")
                else:
                    base = node.module or ""
                targets.append(base)
                targets.extend(f"{base}.{alias.name}" for alias in node.names if alias.name != "*")

            for target in targets:
                dependency = known_module(target)
                if dependency is not None and dependency != source:
                    graph[source].add(dependency)
    return graph


def _transitive_dependencies(graph: dict[str, set[str]], start: str) -> set[str]:
    """Return every production module reachable from *start*."""
    reachable: set[str] = set()
    pending = list(graph[start])
    while pending:
        dependency = pending.pop()
        if dependency in reachable:
            continue
        reachable.add(dependency)
        pending.extend(graph[dependency] - reachable)
    return reachable


def test_server_and_tool_registry_are_not_an_import_cycle() -> None:
    """Keep registration dependent on the acyclic tool-runtime seam."""
    graph = _production_import_graph()
    server_module = "python_refactor_mcp.server"
    registry_module = "python_refactor_mcp.tool_registry"
    runtime_module = "python_refactor_mcp.tool_runtime"

    assert runtime_module in graph[server_module]
    assert runtime_module in graph[registry_module]
    assert registry_module in _transitive_dependencies(graph, server_module)
    assert server_module not in _transitive_dependencies(graph, registry_module)


@pytest.mark.asyncio
async def test_server_registers_expected_tool_surface() -> None:
    """Ensure the current MCP tool surface is registered on the MCP instance."""
    tools = await server.mcp.list_tools()
    names = {tool.name for tool in tools}
    assert DEFAULT_TOOL_PROFILE == "refactoring"
    assert len(tools) == 67
    assert len(tools) < MAX_TOOLS_PER_PROFILE
    assert {"convert_to_dataclass", "prepare_rename", "get_diagnostics", "server_status"} <= names
    assert "check_type_stub_freshness" not in names
    assert "Active tool profile: refactoring" in (server.mcp.instructions or "")
    assert all("ctx" not in tool.input_schema.get("properties", {}) for tool in tools)


@pytest.mark.asyncio
async def test_position_based_tools_document_zero_based_convention() -> None:
    """Every tool taking caller-supplied positions states the 0-based convention.

    Data-driven and drift-proof, mirroring the tool-count gate above: it
    enumerates the live tool surface and selects every tool whose input schema
    exposes a caller-supplied position directly as ``line``/``start_line`` or
    indirectly through the canonical ``Position``/``SymbolAnchor`` models.
    Any future position tool is auto-covered.
    """
    tools = await server.mcp.list_tools()

    def _contains_position_ref(value: object) -> bool:
        if isinstance(value, dict):
            ref = value.get("$ref")
            return (
                isinstance(ref, str)
                and (ref.endswith("/Position") or ref.endswith("/SymbolAnchor"))
            ) or any(_contains_position_ref(child) for child in value.values())
        if isinstance(value, list):
            return any(_contains_position_ref(child) for child in value)
        return False

    position_tools = [
        tool
        for tool in tools
        if {"line", "start_line"} & set(tool.input_schema.get("properties", {}))
        or _contains_position_ref(tool.input_schema.get("properties", {}))
    ]
    # Guard against the selector silently matching nothing (e.g. a schema-shape
    # change), which would make the assertion below vacuously pass.
    assert position_tools, "expected at least one position-based tool in the surface"
    assert {"selection_range", "test_impact_select"} <= {tool.name for tool in position_tools}

    missing = [
        tool.name
        for tool in position_tools
        if POSITION_CONVENTION_PHRASE not in (tool.description or "")
    ]
    assert not missing, (
        f"{len(missing)} position-based tool description(s) missing the 0-based "
        f"convention phrase: {sorted(missing)}"
    )
