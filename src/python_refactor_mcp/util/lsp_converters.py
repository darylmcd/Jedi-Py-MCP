"""Pure LSP ↔ model conversion functions extracted from the Pyright backend."""

from __future__ import annotations

from python_refactor_mcp.models import (
    CallHierarchyItem,
    Diagnostic,
    Location,
    Position,
    Range,
    TypeHierarchyItem,
)
from python_refactor_mcp.util.lsp_client import JSONDict, JSONValue
from python_refactor_mcp.util.paths import path_to_uri, uri_to_path

# ── Symbol / highlight / token kind mappings ──────────────────────────────

SYMBOL_KIND: dict[int, str] = {
    1: "file",
    2: "module",
    3: "namespace",
    4: "package",
    5: "class",
    6: "method",
    7: "property",
    8: "field",
    9: "constructor",
    10: "enum",
    11: "interface",
    12: "function",
    13: "variable",
    14: "constant",
    15: "string",
    16: "number",
    17: "boolean",
    18: "array",
    19: "object",
    20: "key",
    21: "null",
    22: "enumMember",
    23: "struct",
    24: "event",
    25: "operator",
    26: "typeParameter",
}

REVERSE_SYMBOL_KIND: dict[str, int] = {v: k for k, v in SYMBOL_KIND.items()}

DOCUMENT_HIGHLIGHT_KIND: dict[int, str] = {1: "text", 2: "read", 3: "write"}

SEMANTIC_TOKEN_TYPES: list[str] = [
    "namespace",
    "type",
    "class",
    "enum",
    "interface",
    "struct",
    "typeParameter",
    "parameter",
    "variable",
    "property",
    "enumMember",
    "event",
    "function",
    "method",
    "macro",
    "keyword",
    "modifier",
    "comment",
    "string",
    "number",
    "regexp",
    "operator",
    "decorator",
]

SEMANTIC_TOKEN_MODIFIERS: list[str] = [
    "declaration",
    "definition",
    "readonly",
    "static",
    "deprecated",
    "abstract",
    "async",
    "modification",
    "documentation",
    "defaultLibrary",
]


# ── JSON value coercion ───────────────────────────────────────────────────


def as_int(value: JSONValue, fallback: int = 0) -> int:
    """Convert a JSON value to int when possible, otherwise return fallback."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return int(value)
    return fallback


def as_str(value: JSONValue, fallback: str = "") -> str:
    """Convert a JSON value to str when possible, otherwise return fallback."""
    if isinstance(value, str):
        return value
    return fallback


# ── LSP → model primitives ────────────────────────────────────────────────


def model_position(value: JSONDict) -> Position:
    """Convert an LSP position dict into a Position model."""
    return Position(
        line=as_int(value.get("line", 0), 0),
        character=as_int(value.get("character", 0), 0),
    )


def model_range(value: JSONDict) -> Range:
    """Convert an LSP range dict into a Range model."""
    start = value.get("start")
    end = value.get("end")
    if not isinstance(start, dict) or not isinstance(end, dict):
        return Range(start=Position(line=0, character=0), end=Position(line=0, character=0))
    return Range(start=model_position(start), end=model_position(end))


# ── Severity mapping ─────────────────────────────────────────────────────


def severity_to_string(value: int) -> str:
    """Map LSP diagnostic severity numbers to string labels."""
    mapping = {1: "error", 2: "warning", 3: "information", 4: "hint"}
    return mapping.get(value, "information")


def severity_from_string(severity: str) -> int:
    """Convert string severity labels into LSP numeric severity."""
    mapping = {"error": 1, "warning": 2, "information": 3, "hint": 4}
    return mapping.get(severity.lower(), 3)


# ── Error detection ──────────────────────────────────────────────────────


def is_unhandled_method_error(response: JSONDict) -> bool:
    """Return True when server reports an unsupported/unhandled LSP method."""
    error_value = response.get("error")
    if not isinstance(error_value, dict):
        return False
    code = error_value.get("code")
    message = error_value.get("message")
    if code == -32601:
        return True
    return isinstance(message, str) and "Unhandled method" in message


# ── Text processing ──────────────────────────────────────────────────────


def strip_markdown_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences from hover text."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.split("\n")
    if lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def extract_hover_text(contents: JSONValue) -> str:
    """Flatten hover contents into a single text blob."""
    if isinstance(contents, str):
        return strip_markdown_fences(contents)
    if isinstance(contents, dict):
        value = contents.get("value")
        if isinstance(value, str):
            return strip_markdown_fences(value)
        return ""
    if isinstance(contents, list):
        chunks: list[str] = []
        for item in contents:
            flattened = extract_hover_text(item)
            if flattened:
                chunks.append(flattened)
        return "\n".join(chunks)
    return ""


# ── Location / definition converters ─────────────────────────────────────


def definition_entry_to_locations(entry: JSONDict) -> list[Location]:
    """Convert definition response entries (Location/LocationLink) into models."""
    if "uri" in entry and "range" in entry:
        uri_value = entry.get("uri")
        range_value = entry.get("range")
        if isinstance(uri_value, str) and isinstance(range_value, dict):
            return [Location(file_path=uri_to_path(uri_value), range=model_range(range_value))]

    target_uri = entry.get("targetUri")
    target_range = entry.get("targetSelectionRange")
    if not isinstance(target_range, dict):
        target_range = entry.get("targetRange")
    if isinstance(target_uri, str) and isinstance(target_range, dict):
        return [Location(file_path=uri_to_path(target_uri), range=model_range(target_range))]

    return []


# ── Hierarchy item converters ────────────────────────────────────────────


def call_hierarchy_item_to_model(item: JSONDict) -> CallHierarchyItem:
    """Convert an LSP call hierarchy item payload to the project model."""
    uri = as_str(item.get("uri"), "")
    range_value = item.get("selectionRange")
    if not isinstance(range_value, dict):
        range_value = item.get("range")

    mr = model_range(range_value) if isinstance(range_value, dict) else Range(
        start=Position(line=0, character=0),
        end=Position(line=0, character=0),
    )

    kind_number = as_int(item.get("kind"), 13)
    return CallHierarchyItem(
        name=as_str(item.get("name"), ""),
        kind=SYMBOL_KIND.get(kind_number, "symbol"),
        file_path=uri_to_path(uri) if uri else "",
        range=mr,
        detail=as_str(item.get("detail"), "") or None,
    )


def call_hierarchy_item_to_lsp(item: CallHierarchyItem) -> dict[str, JSONValue]:
    """Convert project call hierarchy model to LSP item payload."""
    return {
        "name": item.name,
        "kind": REVERSE_SYMBOL_KIND.get(item.kind, 12),
        "uri": path_to_uri(item.file_path),
        "range": {
            "start": {
                "line": item.range.start.line,
                "character": item.range.start.character,
            },
            "end": {
                "line": item.range.end.line,
                "character": item.range.end.character,
            },
        },
        "selectionRange": {
            "start": {
                "line": item.range.start.line,
                "character": item.range.start.character,
            },
            "end": {
                "line": item.range.end.line,
                "character": item.range.end.character,
            },
        },
        "detail": item.detail or "",
    }


def type_hierarchy_item_to_model(item: JSONDict) -> TypeHierarchyItem:
    """Convert an LSP type hierarchy payload to the project model."""
    uri = as_str(item.get("uri"), "")
    range_value = item.get("selectionRange")
    if not isinstance(range_value, dict):
        range_value = item.get("range")
    mr = model_range(range_value) if isinstance(range_value, dict) else Range(
        start=Position(line=0, character=0),
        end=Position(line=0, character=0),
    )
    kind_number = as_int(item.get("kind"), 5)
    return TypeHierarchyItem(
        name=as_str(item.get("name"), ""),
        kind=SYMBOL_KIND.get(kind_number, "class"),
        file_path=uri_to_path(uri) if uri else "",
        range=mr,
        detail=as_str(item.get("detail"), "") or None,
    )


def type_hierarchy_item_to_lsp(item: TypeHierarchyItem) -> dict[str, JSONValue]:
    """Convert type hierarchy model to LSP TypeHierarchyItem payload."""
    return {
        "name": item.name,
        "kind": REVERSE_SYMBOL_KIND.get(item.kind, 5),
        "uri": path_to_uri(item.file_path),
        "range": {
            "start": {"line": item.range.start.line, "character": item.range.start.character},
            "end": {"line": item.range.end.line, "character": item.range.end.character},
        },
        "selectionRange": {
            "start": {"line": item.range.start.line, "character": item.range.start.character},
            "end": {"line": item.range.end.line, "character": item.range.end.character},
        },
        "detail": item.detail or "",
    }


# ── Diagnostics conversion ──────────────────────────────────────────────


def convert_publish_diagnostics(params: JSONDict) -> tuple[str, list[Diagnostic]]:
    """Convert a publishDiagnostics notification into (file_path, diagnostics).

    Returns ("", []) when the notification payload is malformed.
    """
    uri_value = params.get("uri")
    diagnostics_value = params.get("diagnostics")
    if not isinstance(uri_value, str) or not isinstance(diagnostics_value, list):
        return "", []

    file_path = uri_to_path(uri_value)
    converted: list[Diagnostic] = []
    for entry in diagnostics_value:
        if not isinstance(entry, dict):
            continue

        range_value = entry.get("range")
        message_value = entry.get("message")
        severity_value = entry.get("severity")
        code_value = entry.get("code")

        if not isinstance(range_value, dict) or not isinstance(message_value, str):
            continue

        code: str | None = None
        if isinstance(code_value, str):
            code = code_value
        elif isinstance(code_value, int):
            code = str(code_value)

        tags_value = entry.get("tags")
        tags: list[int] = []
        if isinstance(tags_value, list):
            tags = [tag for tag in tags_value if isinstance(tag, int)]

        converted.append(
            Diagnostic(
                file_path=file_path,
                range=model_range(range_value),
                severity=severity_to_string(as_int(severity_value, 3)),
                message=message_value,
                code=code,
                tags=tags,
            )
        )

    return file_path, converted
