"""Find unused imports using Pyright diagnostics with AST fallback."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Protocol

from python_refactor_mcp.models import Diagnostic, UnusedImport


class _PyrightDiagnosticsBackend(Protocol):
    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]: ...


async def find_unused_imports(
    pyright: _PyrightDiagnosticsBackend,
    file_path: str,
    file_paths: list[str] | None = None,
) -> list[UnusedImport]:
    """Find unused imports using Pyright reportUnusedImport diagnostics."""
    paths = [file_path] if file_paths is None else file_paths
    results: list[UnusedImport] = []

    for fp in paths:
        diagnostics = await pyright.get_diagnostics(fp)
        for diag in diagnostics:
            if "import" in diag.message.lower() and (
                diag.code == "reportUnusedImport"
                or "not accessed" in diag.message.lower()
                or "unused" in diag.message.lower()
            ):
                # __future__ imports are special — they modify runtime behaviour
                # even though their names are never referenced directly in code.
                if "__future__" in diag.message:
                    continue
                # Extract the import name from diagnostic message
                name = _extract_import_name(diag.message)
                results.append(UnusedImport(
                    file_path=diag.file_path,
                    module="",
                    name=name,
                    line=diag.range.start.line,
                    message=diag.message,
                ))

        # AST fallback for any not caught by Pyright
        if not results:
            results.extend(_ast_find_unused(fp))

    return results


def _extract_import_name(message: str) -> str | None:
    """Extract the import name from a diagnostic message."""
    # Typical: '"foo" is not accessed'
    if '"' in message:
        parts = message.split('"')
        if len(parts) >= 2:
            return parts[1]
    return None


def _ast_find_unused(file_path: str) -> list[UnusedImport]:
    """AST-based fallback: compare imported names vs. used names."""
    try:
        content = Path(file_path).read_text(encoding="utf-8")
        tree = ast.parse(content, filename=file_path)
    except (SyntaxError, OSError):
        return []

    imported: dict[str, tuple[str, int]] = {}  # name -> (module, line)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name
                imported[name] = (alias.name, node.lineno - 1)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "__future__":
                continue
            for alias in node.names:
                name = alias.asname or alias.name
                imported[name] = (module, node.lineno - 1)

    # Collect all Name references (excluding imports themselves)
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            # Check the root of attribute chains
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value  # type: ignore[assignment]
            if isinstance(root, ast.Name):
                used.add(root.id)

    results: list[UnusedImport] = []
    for name, (module, line) in imported.items():
        if name not in used:
            results.append(UnusedImport(
                file_path=str(Path(file_path).resolve()),
                module=module,
                name=name,
                line=line,
                message=f"Import '{name}' is not used",
            ))
    return results
