"""Unit tests for server shell behavior."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from mcp.server.mcpserver import MCPServer

from python_refactor_mcp import server
from python_refactor_mcp.config import DEFAULT_TOOL_PROFILE
from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.tool_registry import (
    MAX_TOOLS_PER_PROFILE,
    profile_description,
    register_tools,
    tool_names_for_profile,
)

# Shared 0-based position convention sentence. Every position-based tool
# description must embed this verbatim; this constant is the single source of
# truth the gate below asserts against. Keep it in sync with the wording in
# ``python_refactor_mcp.models.Position`` ("0-based line and character offset").
POSITION_CONVENTION_PHRASE = "Positions are 0-based (line and character offsets, LSP convention)."


@pytest.mark.asyncio
async def test_get_inlay_hints_read_failure_is_backend_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Line-count filesystem details remain internal to the MCP boundary."""
    monkeypatch.setattr(server, "get_current_backends", lambda: object())

    with pytest.raises(BackendError, match="Cannot read file for line count"):
        await server.get_inlay_hints(
            object(),  # type: ignore[arg-type]
            str(tmp_path / "private" / "missing.py"),
            0,
            0,
        )


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
    assert len(tools) == 75
    assert len(tools) < MAX_TOOLS_PER_PROFILE
    assert {
        "convert_to_dataclass",
        "convert_to_pydantic",
        "convert_to_typeddict",
        "convert_function_to_method",
        "convert_method_to_function",
        "docstring_sync",
        "extract_class",
        "fix_circular_imports",
        "prepare_rename",
        "get_diagnostics",
        "server_status",
    } <= names
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


_ADVERTISED = frozenset({"find_references", "get_type_info", "get_signature_help"})


def test_profile_description_prunes_unadvertised_related_items() -> None:
    """Hidden tools drop out of Related while the trailing sentence survives."""
    doc = f"Find refs. Related: prepare_rename, find_references, rename_symbol. {POSITION_CONVENTION_PHRASE}"

    result = profile_description(doc, _ADVERTISED)

    assert result == f"Find refs. Related: find_references. {POSITION_CONVENTION_PHRASE}"


def test_profile_description_drops_empty_related_clause() -> None:
    """A clause with no advertised tools is removed without leaving stray punctuation."""
    assert profile_description("Undo. Related: redo_refactoring.", _ADVERTISED) == "Undo."
    assert (
        profile_description(f"Undo. Related: redo_refactoring. {POSITION_CONVENTION_PHRASE}", _ADVERTISED)
        == f"Undo. {POSITION_CONVENTION_PHRASE}"
    )


def test_profile_description_keeps_parentheticals_with_their_items() -> None:
    """A kept item's parenthetical travels with it, even when it holds commas or periods."""
    doc = (
        "Docs. Related: get_type_info (for type only, e.g. hover), "
        "rename_symbol (any tool, e.g. x), get_signature_help (call-site params)."
    )

    result = profile_description(doc, _ADVERTISED)

    assert result == "Docs. Related: get_type_info (for type only, e.g. hover), get_signature_help (call-site params)."


def test_profile_description_without_related_clause_is_unchanged() -> None:
    """Descriptions without a Related clause pass through verbatim."""
    assert profile_description("Plain text. No hints.", _ADVERTISED) == "Plain text. No hints."
    assert profile_description("", _ADVERTISED) == ""


def test_build_server_instructions_analysis_notes_refactoring_profile() -> None:
    """The analysis profile names no refactoring tool and points at the refactoring profile."""
    advertised = tool_names_for_profile("analysis", extra_records=server.EXPLICIT_TOOL_RECORDS)

    text = server.build_server_instructions("analysis", advertised)

    assert "Active tool profile: analysis" in text
    assert "rename_symbol" not in text
    assert '="refactoring" to use them' in text


# Tools whose ``apply=True`` path replaces existing file content wholesale.
_WHOLE_FILE_REWRITERS = frozenset(
    {
        "apply_code_action",
        "organize_imports",
        "format_code",
        "apply_lint_fixes",
        "apply_type_annotations",
        "expand_star_imports",
        "relatives_to_absolutes",
        "froms_to_imports",
        "handle_long_imports",
    }
)


@pytest.mark.asyncio
async def test_whole_file_rewriters_advertise_destructive_hint() -> None:
    """Rewriters of existing content advertise destructiveHint without changing profile membership."""
    mcp = MCPServer("whole-file rewriter annotations")
    register_tools(mcp, "refactoring", extra_records=server.EXPLICIT_TOOL_RECORDS)
    advertised = {tool.name: tool for tool in await mcp.list_tools()}

    assert advertised.keys() >= _WHOLE_FILE_REWRITERS
    for name in sorted(_WHOLE_FILE_REWRITERS):
        annotations = advertised[name].annotations
        assert annotations is not None, name
        assert annotations.destructive_hint is True, name
        assert annotations.read_only_hint is False, name

    analysis = tool_names_for_profile("analysis", extra_records=server.EXPLICIT_TOOL_RECORDS)
    refactoring = tool_names_for_profile("refactoring", extra_records=server.EXPLICIT_TOOL_RECORDS)
    assert refactoring >= _WHOLE_FILE_REWRITERS
    assert not _WHOLE_FILE_REWRITERS & analysis
    assert (len(analysis), len(refactoring)) == (56, 75)
