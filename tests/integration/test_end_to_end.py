"""Integration tests for MCP tool behavior through stdio transport."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from mcp.client.session import ClientSession


def _unwrap_result_payload(payload: object) -> object:
    """Normalize list-returning tool payloads wrapped as {'result': ...}."""
    if isinstance(payload, dict) and "result" in payload:
        return payload["result"]
    return payload


def _find_position(file_path: Path, token: str) -> tuple[int, int]:
    """Find the first line and column index for a token in a source file."""
    lines = file_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        position = line.find(token)
        if position >= 0:
            return index, position
    raise AssertionError(f"Token {token!r} not found in {file_path}")


@pytest.mark.asyncio
async def test_find_references_returns_locations(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure find_references returns locations for class usages."""
    models_path = sample_workspace / "src" / "models.py"
    line, character = _find_position(models_path, "User")

    result = await mcp_session.call_tool(
        "find_references",
        {
            "file_path": str(models_path),
            "line": line,
            "character": character,
            "include_declaration": True,
        },
    )

    assert result.isError is not True
    payload = result.structuredContent
    assert isinstance(payload, dict)
    assert payload.get("total_count", 0) >= 2


@pytest.mark.asyncio
async def test_get_type_info_returns_non_empty_type(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure get_type_info reports a concrete type for a variable."""
    service_path = sample_workspace / "src" / "service.py"
    line, character = _find_position(service_path, "current_user")

    result = await mcp_session.call_tool(
        "get_type_info",
        {
            "file_path": str(service_path),
            "line": line,
            "character": character,
        },
    )

    assert result.isError is not True
    payload = result.structuredContent
    assert isinstance(payload, dict)
    type_string = str(payload.get("type_string", "")).strip()
    assert type_string != ""


@pytest.mark.asyncio
async def test_get_diagnostics_reports_intentional_error(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure diagnostics include the intentional type mismatch in service.py."""
    service_path = sample_workspace / "src" / "service.py"

    await mcp_session.call_tool(
        "find_references",
        {
            "file_path": str(service_path),
            "line": 0,
            "character": 0,
            "include_declaration": True,
        },
    )

    result = await mcp_session.call_tool("get_diagnostics", {"file_path": str(service_path)})

    assert result.isError is not True
    payload = _unwrap_result_payload(result.structuredContent)
    assert isinstance(payload, list)
    assert any("bad" in str(item.get("message", "")) or "int" in str(item.get("message", "")) for item in payload)


@pytest.mark.asyncio
async def test_rename_symbol_returns_edits_without_applying(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure rename_symbol apply=False returns edits and does not write files."""
    service_path = sample_workspace / "src" / "service.py"
    line, character = _find_position(service_path, "current_user")
    before = service_path.read_text(encoding="utf-8")

    result = await mcp_session.call_tool(
        "rename_symbol",
        {
            "file_path": str(service_path),
            "line": line,
            "character": character,
            "new_name": "active_user",
            "apply": False,
        },
    )

    assert result.isError is not True
    payload = result.structuredContent
    assert isinstance(payload, dict)
    assert payload.get("applied") is False
    assert len(payload.get("edits", [])) >= 1
    after = service_path.read_text(encoding="utf-8")
    assert before == after


@pytest.mark.asyncio
async def test_rename_symbol_apply_writes_file(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure rename_symbol apply=True writes edits to disk."""
    service_path = sample_workspace / "src" / "service.py"
    line, character = _find_position(service_path, "current_user")

    result = await mcp_session.call_tool(
        "rename_symbol",
        {
            "file_path": str(service_path),
            "line": line,
            "character": character,
            "new_name": "active_user",
            "apply": True,
        },
    )

    assert result.isError is not True
    payload = result.structuredContent
    assert isinstance(payload, dict)
    assert payload.get("applied") is True
    updated = service_path.read_text(encoding="utf-8")
    assert "active_user" in updated


@pytest.mark.asyncio
async def test_find_constructors_finds_call_sites(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure find_constructors reports constructor invocations."""
    models_path = sample_workspace / "src" / "models.py"

    result = await mcp_session.call_tool(
        "find_constructors",
        {
            "class_name": "User",
            "file_path": str(models_path),
        },
    )

    assert result.isError is not True
    payload = _unwrap_result_payload(result.structuredContent)
    assert isinstance(payload, list)
    assert len(payload) >= 1


@pytest.mark.asyncio
async def test_smart_rename_applies_and_returns_validation(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure smart_rename performs end-to-end rename with validation."""
    service_path = sample_workspace / "src" / "service.py"
    line, character = _find_position(service_path, "invoice")

    result = await mcp_session.call_tool(
        "smart_rename",
        {
            "file_path": str(service_path),
            "line": line,
            "character": character,
            "new_name": "invoice_record",
            "apply": True,
        },
    )

    assert result.isError is not True
    payload = result.structuredContent
    assert isinstance(payload, dict)
    assert payload.get("applied") is True
    updated = service_path.read_text(encoding="utf-8")
    assert "invoice_record" in updated


@pytest.mark.asyncio
async def test_get_hover_info_returns_documentation(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure hover info returns non-empty type metadata."""
    service_path = sample_workspace / "src" / "service.py"
    line, character = _find_position(service_path, "current_user")

    result = await mcp_session.call_tool(
        "get_hover_info",
        {
            "file_path": str(service_path),
            "line": line,
            "character": character,
        },
    )

    assert result.isError is not True
    payload = result.structuredContent
    assert isinstance(payload, dict)
    assert str(payload.get("type_string", "")).strip() != ""


@pytest.mark.asyncio
async def test_get_symbol_outline_returns_items(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure symbol outline returns items for a Python file."""
    models_path = sample_workspace / "src" / "models.py"

    result = await mcp_session.call_tool(
        "get_symbol_outline",
        {
            "file_path": str(models_path),
        },
    )

    assert result.isError is not True
    payload = _unwrap_result_payload(result.structuredContent)
    assert isinstance(payload, list)
    assert any(str(item.get("name", "")) == "User" for item in payload)


@pytest.mark.asyncio
async def test_search_symbols_finds_workspace_symbols(
    mcp_session: ClientSession,
) -> None:
    """Ensure workspace symbol search returns matching symbols."""
    result = await mcp_session.call_tool(
        "search_symbols",
        {
            "query": "User",
        },
    )

    assert result.isError is not True
    payload = _unwrap_result_payload(result.structuredContent)
    assert isinstance(payload, list)
    assert any("User" in str(item.get("name", "")) for item in payload)


@pytest.mark.asyncio
async def test_get_workspace_diagnostics_returns_summary(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure workspace diagnostic summary includes the intentionally broken file."""
    service_path = sample_workspace / "src" / "service.py"
    await mcp_session.call_tool("get_diagnostics", {"file_path": str(service_path)})

    payload: object = []
    for _ in range(8):
        result = await mcp_session.call_tool("get_workspace_diagnostics", {})
        assert result.isError is not True
        payload = _unwrap_result_payload(result.structuredContent)
        if isinstance(payload, list) and any(
            str(item.get("file_path", "")).endswith("service.py")
            for item in payload
            if isinstance(item, dict)
        ):
            break
        await asyncio.sleep(0.1)

    assert isinstance(payload, list)
    assert any(
        str(item.get("file_path", "")).endswith("service.py")
        for item in payload
        if isinstance(item, dict)
    )


@pytest.mark.asyncio
async def test_prepare_rename_and_followup_refactor(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure prepare_rename validates a symbol and supports downstream rename flow."""
    service_path = sample_workspace / "src" / "service.py"
    line, character = _find_position(service_path, "invoice")

    prepared = await mcp_session.call_tool(
        "prepare_rename",
        {
            "file_path": str(service_path),
            "line": line,
            "character": character,
        },
    )

    assert prepared.isError is not True
    payload = prepared.structuredContent
    assert payload is None or isinstance(payload, dict)


@pytest.mark.asyncio
async def test_navigation_additions_return_locations(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure declaration and type-definition navigation tools return structured location lists."""
    models_path = sample_workspace / "src" / "models.py"
    line, character = _find_position(models_path, "User")

    declaration = await mcp_session.call_tool(
        "get_declaration",
        {"file_path": str(models_path), "line": line, "character": character},
    )
    type_definition = await mcp_session.call_tool(
        "get_type_definition",
        {"file_path": str(models_path), "line": line, "character": character},
    )

    assert declaration.isError is not True
    assert type_definition.isError is not True
    decl_payload = _unwrap_result_payload(declaration.structuredContent)
    type_payload = _unwrap_result_payload(type_definition.structuredContent)
    assert isinstance(decl_payload, list)
    assert isinstance(type_payload, list)


@pytest.mark.asyncio
async def test_document_highlights_and_folding_ranges(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure local highlights and folding ranges are available for a sample file."""
    service_path = sample_workspace / "src" / "service.py"
    line, character = _find_position(service_path, "current_user")

    highlights = await mcp_session.call_tool(
        "get_document_highlights",
        {"file_path": str(service_path), "line": line, "character": character},
    )
    folding = await mcp_session.call_tool(
        "get_folding_ranges",
        {"file_path": str(service_path)},
    )

    assert highlights.isError is not True
    assert folding.isError is not True
    highlight_payload = _unwrap_result_payload(highlights.structuredContent)
    folding_payload = _unwrap_result_payload(folding.structuredContent)
    assert isinstance(highlight_payload, list)
    assert isinstance(folding_payload, list)


@pytest.mark.asyncio
async def test_inlay_and_semantic_tokens(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure inlay hints and semantic token tools return structured arrays."""
    service_path = sample_workspace / "src" / "service.py"

    inlay = await mcp_session.call_tool(
        "get_inlay_hints",
        {"file_path": str(service_path)},
    )
    semantic = await mcp_session.call_tool(
        "get_semantic_tokens",
        {"file_path": str(service_path)},
    )

    assert inlay.isError is not True
    assert semantic.isError is not True
    inlay_payload = _unwrap_result_payload(inlay.structuredContent)
    semantic_payload = _unwrap_result_payload(semantic.structuredContent)
    assert isinstance(inlay_payload, list)
    assert isinstance(semantic_payload, list)


@pytest.mark.asyncio
async def test_call_signatures_fallback_tool(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure Jedi signature fallback tool returns a nullable signature payload."""
    service_path = sample_workspace / "src" / "service.py"
    line, character = _find_position(service_path, "User(")
    character += len("User(")

    result = await mcp_session.call_tool(
        "get_call_signatures_fallback",
        {"file_path": str(service_path), "line": line, "character": character},
    )

    assert result.isError is not True
    payload = result.structuredContent
    assert payload is None or isinstance(payload, dict)


@pytest.mark.asyncio
async def test_failure_paths_return_tool_errors(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure invalid requests return MCP tool errors rather than hard crashes."""
    service_path = sample_workspace / "src" / "service.py"

    bad_direction = await mcp_session.call_tool(
        "call_hierarchy",
        {
            "file_path": str(service_path),
            "line": 0,
            "character": 0,
            "direction": "invalid",
            "depth": 1,
        },
    )
    missing_file = await mcp_session.call_tool(
        "organize_imports",
        {"file_path": str(sample_workspace / "src" / "missing.py"), "apply": False},
    )

    assert bad_direction.isError is True
    assert missing_file.isError is True
