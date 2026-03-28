"""Public API extraction from modules."""

from __future__ import annotations

import ast
from pathlib import Path

from python_refactor_mcp.models import PublicAPIItem


def _extract_all_names(tree: ast.Module) -> list[str] | None:
    """Extract names from ``__all__`` if present, else return None."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__" and isinstance(node.value, (ast.List, ast.Tuple)):
                    return [elt.value for elt in node.value.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
    return None


def _classify_symbol(node: ast.stmt) -> tuple[str, str] | None:
    """Return (name, kind) for a module-level symbol or None if not classifiable."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return node.name, "function"
    if isinstance(node, ast.ClassDef):
        return node.name, "class"
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                return target.id, "variable"
    return None


def _should_include(name: str, all_names: list[str] | None) -> bool:
    """Return whether a symbol should appear in the public API."""
    if all_names is not None:
        return name in all_names
    return not name.startswith("_")


async def get_module_public_api(file_path: str) -> list[PublicAPIItem]:
    """Return only exported symbols from a module, respecting __all__ and _ prefix filtering."""
    resolved = str(Path(file_path).resolve())
    content = Path(file_path).read_text(encoding="utf-8")
    tree = ast.parse(content, filename=file_path)

    all_names = _extract_all_names(tree)

    items: list[PublicAPIItem] = []
    for node in tree.body:
        symbol = _classify_symbol(node)
        if symbol is None:
            continue
        name, kind = symbol
        if not _should_include(name, all_names):
            continue
        items.append(PublicAPIItem(
            name=name,
            kind=kind,
            line=node.lineno - 1,
            file_path=resolved,
        ))

    return items
