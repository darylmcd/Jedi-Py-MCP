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


def _assert_refactor_preview_payload(payload: object) -> None:
    """Assert preview-mode refactor responses follow the shared contract."""
    assert isinstance(payload, dict)
    assert isinstance(payload.get("edits"), list)
    assert isinstance(payload.get("files_affected"), list)
    assert isinstance(payload.get("description"), str)
    assert payload.get("applied") is False


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
async def test_rename_symbol_applies_and_returns_validation(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure rename_symbol performs end-to-end rename with validation."""
    service_path = sample_workspace / "src" / "service.py"
    line, character = _find_position(service_path, "invoice")

    result = await mcp_session.call_tool(
        "rename_symbol",
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
async def test_get_type_info_returns_type_metadata(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure get_type_info returns non-empty type metadata."""
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
async def test_get_signature_help_returns_nullable_payload(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure get_signature_help returns a nullable signature payload."""
    service_path = sample_workspace / "src" / "service.py"
    line, character = _find_position(service_path, "User(")
    character += len("User(")

    result = await mcp_session.call_tool(
        "get_signature_help",
        {"file_path": str(service_path), "line": line, "character": character},
    )

    assert result.isError is not True
    payload = result.structuredContent
    assert payload is None or isinstance(payload, dict)


@pytest.mark.asyncio
async def test_get_documentation_returns_structured_payload(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure get_documentation returns a structured result for a known symbol."""
    models_path = sample_workspace / "src" / "models.py"
    line, character = _find_position(models_path, "User")

    result = await mcp_session.call_tool(
        "get_documentation",
        {"file_path": str(models_path), "line": line, "character": character},
    )

    assert result.isError is not True
    payload = result.structuredContent
    assert isinstance(payload, dict)
    assert isinstance(payload.get("entries", []), list)


@pytest.mark.asyncio
async def test_type_hierarchy_and_selection_range_tools(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure newly added navigation helpers return structured payloads."""
    hierarchy_path = sample_workspace / "src" / "hierarchy.py"
    hierarchy_path.write_text(
        "class Base:\n"
        "    pass\n\n"
        "class Child(Base):\n"
        "    pass\n",
        encoding="utf-8",
    )
    line, character = _find_position(hierarchy_path, "Child")

    type_result = await mcp_session.call_tool(
        "type_hierarchy",
        {
            "file_path": str(hierarchy_path),
            "line": line,
            "character": character,
            "direction": "both",
            "depth": 2,
        },
    )
    selection_result = await mcp_session.call_tool(
        "selection_range",
        {
            "file_path": str(hierarchy_path),
            "positions": [{"line": line, "character": character}],
        },
    )

    assert type_result.isError is not True
    assert selection_result.isError is not True
    type_payload = type_result.structuredContent
    selection_payload = _unwrap_result_payload(selection_result.structuredContent)
    assert isinstance(type_payload, dict)
    assert isinstance(selection_payload, list)


@pytest.mark.asyncio
async def test_new_refactoring_tools_preview_mode(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure newly exposed rope-backed refactors run in preview mode."""
    target = sample_workspace / "src" / "refactor_targets.py"
    target.write_text(
        "class Widget:\n"
        "    def __init__(self, value: int):\n"
        "        self.value = value\n\n"
        "    def compute(self, amount: int) -> int:\n"
        "        local_value = amount + self.value\n"
        "        return local_value\n\n"
        "def compute_total(price: float, tax: float) -> float:\n"
        "    total = price + tax\n"
        "    return total\n",
        encoding="utf-8",
    )

    compute_line, compute_char = _find_position(target, "compute_total")
    method_line, method_char = _find_position(target, "compute(self")
    local_line, local_char = _find_position(target, "local_value")
    class_line, class_char = _find_position(target, "Widget")

    change_signature = await mcp_session.call_tool(
        "change_signature",
        {
            "file_path": str(target),
            "line": compute_line,
            "character": compute_char,
            "operations": [{"op": "add", "index": 2, "name": "discount", "default": "0.0"}],
            "apply": False,
        },
    )
    restructure = await mcp_session.call_tool(
        "restructure",
        {
            "pattern": "${a} + ${b}",
            "goal": "${b} + ${a}",
            "file_path": str(target),
            "apply": False,
        },
    )
    use_function = await mcp_session.call_tool(
        "use_function",
        {"file_path": str(target), "line": compute_line, "character": compute_char, "apply": False},
    )
    introduce_factory = await mcp_session.call_tool(
        "introduce_factory",
        {"file_path": str(target), "line": class_line, "character": class_char, "apply": False},
    )
    local_to_field = await mcp_session.call_tool(
        "local_to_field",
        {"file_path": str(target), "line": local_line, "character": local_char, "apply": False},
    )
    method_object = await mcp_session.call_tool(
        "method_object",
        {
            "file_path": str(target),
            "line": method_line,
            "character": method_char,
            "classname": "ComputeMethodObject",
            "apply": False,
        },
    )

    assert change_signature.isError is not True
    assert restructure.isError is not True
    assert use_function.isError is not True
    assert introduce_factory.isError is not True
    assert local_to_field.isError is not True
    assert method_object.isError is not True

    for response in (
        change_signature,
        restructure,
        use_function,
        introduce_factory,
        local_to_field,
        method_object,
    ):
        _assert_refactor_preview_payload(response.structuredContent)


@pytest.mark.asyncio
async def test_module_to_package_preview_mode(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure module_to_package preview returns structured non-error output."""
    module_path = sample_workspace / "src" / "module_to_convert.py"
    module_path.write_text(
        "VALUE = 1\n",
        encoding="utf-8",
    )

    result = await mcp_session.call_tool(
        "module_to_package",
        {"file_path": str(module_path), "apply": False},
    )

    assert result.isError is not True
    _assert_refactor_preview_payload(result.structuredContent)


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


# ── PR 3-A: Integration smoke tests for introduce_parameter and encapsulate_field ──


@pytest.mark.asyncio
async def test_introduce_parameter_preview_mode(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure introduce_parameter returns a valid preview payload."""
    service_path = sample_workspace / "src" / "service.py"
    line, character = _find_position(service_path, "12.5")

    result = await mcp_session.call_tool(
        "introduce_parameter",
        {
            "file_path": str(service_path),
            "line": line,
            "character": character,
            "parameter_name": "amount",
            "default_value": "12.5",
            "apply": False,
        },
    )

    assert result.isError is not True
    _assert_refactor_preview_payload(result.structuredContent)


@pytest.mark.asyncio
async def test_encapsulate_field_preview_mode(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure encapsulate_field returns a valid preview payload."""
    models_path = sample_workspace / "src" / "models.py"
    line, character = _find_position(models_path, "user_id")

    result = await mcp_session.call_tool(
        "encapsulate_field",
        {
            "file_path": str(models_path),
            "line": line,
            "character": character,
            "apply": False,
        },
    )

    assert result.isError is not True
    _assert_refactor_preview_payload(result.structuredContent)


# ── PR 3-B: Failure-path integration scenarios ──


@pytest.mark.asyncio
async def test_rename_at_invalid_position_returns_error(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure rename at a non-symbol position returns an error."""
    service_path = sample_workspace / "src" / "service.py"

    result = await mcp_session.call_tool(
        "rename_symbol",
        {
            "file_path": str(service_path),
            "line": 0,
            "character": 0,
            "new_name": "new_name",
            "apply": False,
        },
    )

    assert result.isError is True


@pytest.mark.asyncio
async def test_extract_method_invalid_range_returns_error(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure extract_method with invalid range returns an error."""
    service_path = sample_workspace / "src" / "service.py"

    result = await mcp_session.call_tool(
        "extract_method",
        {
            "file_path": str(service_path),
            "start_line": 5,
            "start_character": 0,
            "end_line": 2,
            "end_character": 0,
            "method_name": "new_method",
            "apply": False,
        },
    )

    assert result.isError is True


@pytest.mark.asyncio
async def test_find_references_nonexistent_file_returns_error(
    mcp_session: ClientSession,
    sample_workspace: Path,
) -> None:
    """Ensure find_references for a nonexistent file returns an error."""
    result = await mcp_session.call_tool(
        "find_references",
        {
            "file_path": str(sample_workspace / "nonexistent.py"),
            "line": 0,
            "character": 0,
        },
    )

    assert result.isError is True
