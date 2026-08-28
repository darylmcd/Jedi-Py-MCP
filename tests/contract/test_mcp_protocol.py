"""MCP protocol contract tests.

Verify that the server exposes correct capabilities, tool metadata,
annotations, and schema shapes per the MCP specification.
"""

from __future__ import annotations

import pytest

from python_refactor_mcp import server


@pytest.mark.asyncio
async def test_tool_count_within_limits() -> None:
    """Tool count should not exceed the 30-40 tool LLM reliability threshold by too much."""
    tools = await server.mcp.list_tools()
    # 88 tools after format_code; soft cap tracks actual surface + small headroom.
    assert len(tools) <= 100, f"Tool count {len(tools)} exceeds soft limit of 100"


@pytest.mark.asyncio
async def test_all_tools_have_annotations() -> None:
    """Every tool must have explicit MCP read-only and destructive annotations."""
    tools = await server.mcp.list_tools()
    for tool in tools:
        assert tool.annotations is not None, f"Tool '{tool.name}' is missing annotations"
        assert tool.annotations.read_only_hint is not None, f"Tool '{tool.name}' missing read_only_hint"
        assert tool.annotations.destructive_hint is not None, f"Tool '{tool.name}' missing destructive_hint"
        assert tool.annotations.open_world_hint is not None, f"Tool '{tool.name}' missing open_world_hint"


@pytest.mark.asyncio
async def test_readonly_tools_are_idempotent() -> None:
    """Read-only tools should be marked idempotent."""
    tools = await server.mcp.list_tools()
    for tool in tools:
        if tool.annotations and tool.annotations.read_only_hint:
            assert tool.annotations.idempotent_hint is True, (
                f"Read-only tool '{tool.name}' should have idempotent_hint=True"
            )


@pytest.mark.asyncio
async def test_destructive_tools_have_apply_parameter() -> None:
    """Destructive and additive tools should have an 'apply' parameter defaulting to False."""
    tools = await server.mcp.list_tools()
    # Tools that are destructive or additive (readOnly=False)
    # Tools without apply: preview-only, queries, or history/stack operations that act immediately.
    skip_tools = {
        "prepare_rename", "diff_preview", "create_type_stubs", "autoimport_search",
        "restart_server", "undo_refactoring", "redo_refactoring",
        "begin_change_stack", "commit_change_stack", "rollback_change_stack",
        # Atomic multi-tool transaction: commits all steps under one change-stack
        # or rolls back — an immediately-acting stack operation, no preview/apply split.
        "refactor_transaction",
    }
    for tool in tools:
        if tool.annotations and not tool.annotations.read_only_hint and tool.name not in skip_tools:
            props = tool.input_schema.get("properties", {})
            assert "apply" in props, f"Non-readonly tool '{tool.name}' should have 'apply' parameter"


@pytest.mark.asyncio
async def test_no_ctx_in_schemas() -> None:
    """The internal ctx parameter must never appear in tool schemas."""
    tools = await server.mcp.list_tools()
    for tool in tools:
        props = tool.input_schema.get("properties", {})
        assert "ctx" not in props, f"Tool '{tool.name}' exposes internal 'ctx' parameter"


@pytest.mark.asyncio
async def test_tool_descriptions_are_workflow_oriented() -> None:
    """Tool descriptions should be longer than 50 chars and mention related tools."""
    tools = await server.mcp.list_tools()
    short_description_tools = []
    for tool in tools:
        desc = tool.description or ""
        if len(desc) < 50:
            short_description_tools.append(tool.name)
    assert not short_description_tools, (
        f"These tools have descriptions under 50 chars (should be workflow-oriented): {short_description_tools}"
    )


@pytest.mark.asyncio
async def test_server_has_version() -> None:
    """Server should expose its version matching the package version."""
    assert server.mcp.name == "Python Refactor"
    assert server.mcp.version == server.__version__


@pytest.mark.asyncio
async def test_annotation_variants_exist() -> None:
    """Server should use all three annotation variants: READONLY, DESTRUCTIVE, ADDITIVE."""
    tools = await server.mcp.list_tools()
    annotations = [t.annotations for t in tools if t.annotations is not None]
    assert any(a.read_only_hint for a in annotations), "No tools use READONLY annotations"
    assert any(a.destructive_hint for a in annotations), "No tools use DESTRUCTIVE annotations"
    assert any(
        not a.read_only_hint and not a.destructive_hint for a in annotations
    ), "No tools use ADDITIVE annotations"


@pytest.mark.asyncio
async def test_path_params_are_validated() -> None:
    """All known path parameter names should be in the validation tuple.

    Order matters: source/subject paths must come before destination paths so
    that move/copy tools anchor workspace resolution on the source, not the
    destination.
    """
    path_params = server._PATH_PARAMS  # pyright: ignore[reportPrivateUsage]
    expected_members = {"file_path", "source_file", "destination_file", "root_path", "source_path", "destination_package"}
    assert expected_members == set(path_params)
    # Source/subject paths must precede destination paths.
    for src in ("file_path", "source_file", "source_path"):
        for dst in ("destination_file", "destination_package"):
            assert path_params.index(src) < path_params.index(dst), (
                f"{src!r} must come before {dst!r} in _PATH_PARAMS"
            )


@pytest.mark.asyncio
async def test_identifier_params_are_validated() -> None:
    """All known identifier parameter names should be in the validation tuple."""
    expected = {"new_name", "method_name", "variable_name", "parameter_name", "factory_name", "classname"}
    assert expected == set(server._IDENTIFIER_PARAMS)  # pyright: ignore[reportPrivateUsage]
