"""Public API extraction from modules."""

from __future__ import annotations

import ast
from pathlib import Path

from python_refactor_mcp.models import PublicAPIItem


async def get_module_public_api(file_path: str) -> list[PublicAPIItem]:
    """Return only exported symbols from a module, respecting __all__ and _ prefix filtering."""
    resolved = str(Path(file_path).resolve())
    content = Path(file_path).read_text(encoding="utf-8")
    tree = ast.parse(content, filename=file_path)

    # Check for __all__
    all_names: list[str] | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        all_names = []
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                all_names.append(elt.value)

    items: list[PublicAPIItem] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            kind = "function"
        elif isinstance(node, ast.ClassDef):
            name = node.name
            kind = "class"
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    kind = "variable"
                    break
            else:
                continue
        else:
            continue

        if all_names is not None:
            if name not in all_names:
                continue
        elif name.startswith("_"):
            continue

        items.append(PublicAPIItem(
            name=name,
            kind=kind,
            line=node.lineno - 1,
            file_path=resolved,
        ))

    return items
