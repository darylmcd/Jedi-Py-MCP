"""Find unused imports using Pyright diagnostics with AST fallback."""

from __future__ import annotations

import ast
from typing import Protocol

from python_refactor_mcp.models import Diagnostic, ScanFailure, UnusedImport, UnusedImportScanResult
from python_refactor_mcp.util.scan import ParsedPythonFile, parse_python_file


class _PyrightDiagnosticsBackend(Protocol):
    async def get_diagnostics(self, file_path: str | None) -> list[Diagnostic]: ...


async def find_unused_imports(
    pyright: _PyrightDiagnosticsBackend,
    file_path: str,
    file_paths: list[str] | None = None,
) -> UnusedImportScanResult:
    """Find unused imports using Pyright reportUnusedImport diagnostics."""
    paths = [file_path] if file_paths is None else file_paths
    results: list[UnusedImport] = []
    scan_failures: list[ScanFailure] = []

    for fp in paths:
        parsed, failure = parse_python_file(fp)
        if parsed is None:
            if failure is not None:
                scan_failures.append(failure)
            continue

        # Read __all__ exports to avoid false positives on re-export facades.
        all_exports = _read_all_exports(parsed)

        try:
            diagnostics = await pyright.get_diagnostics(str(parsed.path))
        except Exception as exc:
            scan_failures.append(
                ScanFailure(
                    file_path=str(parsed.path),
                    phase="diagnostics",
                    error_type=type(exc).__name__,
                )
            )
            diagnostics = []

        file_results: list[UnusedImport] = []
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
                # Skip imports listed in __all__ (intentional re-exports).
                if name is not None and name in all_exports:
                    continue
                file_results.append(UnusedImport(
                    file_path=diag.file_path,
                    module="",
                    name=name,
                    line=diag.range.start.line,
                    message=diag.message,
                ))

        # AST fallback fills gaps in Pyright's diagnostics. Merge by binding and
        # line so one diagnostic cannot suppress other unused imports in the file.
        seen = {(item.name, item.line) for item in file_results}
        for fallback in _ast_find_unused(parsed):
            if fallback.name in all_exports or (fallback.name, fallback.line) in seen:
                continue
            file_results.append(fallback)
        results.extend(file_results)

    return UnusedImportScanResult(
        items=results,
        files_scanned=len(paths) - sum(1 for failure in scan_failures if failure.phase == "read_or_parse"),
        scan_failures=scan_failures,
    )


def _read_all_exports(parsed: ParsedPythonFile) -> set[str]:
    """Read names from ``__all__`` in the given file, if present."""
    for node in parsed.tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "__all__"
                    and isinstance(node.value, (ast.List, ast.Tuple))
                ):
                    return {
                        elt.value
                        for elt in node.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    }
    return set()


def _extract_import_name(message: str) -> str | None:
    """Extract the import name from a diagnostic message."""
    # Typical: '"foo" is not accessed'
    if '"' in message:
        parts = message.split('"')
        if len(parts) >= 2:
            return parts[1]
    return None


def _ast_find_unused(parsed: ParsedPythonFile) -> list[UnusedImport]:
    """AST-based fallback: compare imported names vs. used names."""
    imported: dict[str, tuple[str, int]] = {}  # name -> (module, line)
    for node in ast.walk(parsed.tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # ``import package.submodule`` binds only ``package`` unless
                # the import has an explicit alias.
                name = alias.asname or alias.name.split(".", maxsplit=1)[0]
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
    for node in ast.walk(parsed.tree):
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
                file_path=str(parsed.path),
                module=module,
                name=name,
                line=line,
                message=f"Import '{name}' is not used",
            ))
    return results
