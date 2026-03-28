"""Suggest imports for unresolved symbols."""

from __future__ import annotations

import re

from python_refactor_mcp.models import ImportSuggestion

from ._helpers import (
    JediSearchBackend,
    PyrightSearchBackend,
)

_UNRESOLVED_PATTERNS = (
    "is not defined",
    "cannot be resolved",
    "unknown import symbol",
    "name",
)


def _as_import_suggestion(symbol: str, statement: str) -> ImportSuggestion | None:
    """Parse an import statement into an import suggestion model."""
    normalized = statement.strip()
    from_match = re.match(r"from\s+([\w.]+)\s+import\s+(.+)", normalized)
    if from_match:
        return ImportSuggestion(
            symbol=symbol,
            module=from_match.group(1),
            import_statement=normalized,
        )

    import_match = re.match(r"import\s+([\w.]+)", normalized)
    if import_match:
        return ImportSuggestion(
            symbol=symbol,
            module=import_match.group(1),
            import_statement=normalized,
        )

    return None


def _extract_import_lines_from_action(action: dict[str, object], symbol: str) -> list[ImportSuggestion]:
    """Extract import suggestions from a code action payload."""
    suggestions: list[ImportSuggestion] = []
    candidates: list[str] = []

    title = action.get("title")
    if isinstance(title, str):
        candidates.extend(re.findall(r"(?:from\s+[\w.]+\s+import\s+[^\n]+|import\s+[\w.]+)", title))

    edit = action.get("edit")
    if isinstance(edit, dict):
        changes = edit.get("changes")
        if isinstance(changes, dict):
            for value in changes.values():
                if not isinstance(value, list):
                    continue
                for entry in value:
                    if not isinstance(entry, dict):
                        continue
                    new_text = entry.get("newText")
                    if isinstance(new_text, str):
                        candidates.extend(
                            re.findall(
                                r"(?:from\s+[\w.]+\s+import\s+[^\n]+|import\s+[\w.]+)",
                                new_text,
                            )
                        )

    for candidate in candidates:
        suggestion = _as_import_suggestion(symbol, candidate)
        if suggestion is not None:
            suggestions.append(suggestion)
    return suggestions


async def suggest_imports(
    pyright: PyrightSearchBackend,
    jedi: JediSearchBackend,
    symbol: str,
    file_path: str,
) -> list[ImportSuggestion]:
    """Suggest imports for an unresolved symbol in a file context."""
    diagnostics = await pyright.get_diagnostics(file_path)
    unresolved = [
        diagnostic
        for diagnostic in diagnostics
        if symbol in diagnostic.message
        and any(pattern in diagnostic.message.lower() for pattern in _UNRESOLVED_PATTERNS)
    ]

    pyright_suggestions: list[ImportSuggestion] = []
    for diagnostic in unresolved:
        actions = await pyright.get_code_actions(file_path, diagnostic.range, [diagnostic])
        for action in actions:
            pyright_suggestions.extend(_extract_import_lines_from_action(action, symbol))

    jedi_suggestions = await jedi.search_names(symbol)

    deduped: dict[tuple[str, str], ImportSuggestion] = {}
    for suggestion in pyright_suggestions + jedi_suggestions:
        key = (suggestion.symbol, suggestion.module)
        if key not in deduped:
            deduped[key] = suggestion

    return sorted(deduped.values(), key=lambda item: (item.module, item.import_statement))
