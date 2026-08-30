"""Duplicated code detection using AST normalization and hashing."""

from __future__ import annotations

import ast
import hashlib
from collections import defaultdict

from python_refactor_mcp.models import DuplicateCodeResult, DuplicateGroup, ScanFailure
from python_refactor_mcp.util.scan import parse_python_file


class _Normalizer(ast.NodeTransformer):
    """Normalize variable names to detect structural duplicates."""

    def visit_Name(self, node: ast.Name) -> ast.Name:  # noqa: N802
        node.id = "_"
        return node

    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = "_"
        return node


async def find_duplicated_code(
    file_path: str,
    file_paths: list[str] | None = None,
    min_lines: int = 3,
) -> DuplicateCodeResult:
    """Find duplicated function bodies by normalizing AST and hashing."""
    paths = [file_path] if file_paths is None else file_paths
    bodies: dict[str, list[dict[str, object]]] = defaultdict(list)
    scan_failures: list[ScanFailure] = []

    for fp in paths:
        parsed, failure = parse_python_file(fp)
        if parsed is None:
            if failure is not None:
                scan_failures.append(failure)
            continue

        for node in ast.walk(parsed.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.body:
                    continue
                loc = (node.end_lineno or node.lineno) - node.lineno + 1
                if loc < min_lines:
                    continue
                # Normalize and hash the body
                body_ast = ast.Module(body=node.body, type_ignores=[])
                normalized = _Normalizer().visit(ast.parse(ast.unparse(body_ast)))
                dump = ast.dump(normalized)
                h = hashlib.md5(dump.encode(), usedforsecurity=False).hexdigest()
                bodies[h].append({
                    "file_path": str(parsed.path),
                    "function_name": node.name,
                    "line": node.lineno - 1,
                    "end_line": (node.end_lineno or node.lineno) - 1,
                })

    groups: list[DuplicateGroup] = []
    for h, occurrences in bodies.items():
        if len(occurrences) < 2:
            continue
        groups.append(DuplicateGroup(
            hash=h,
            function_name=occurrences[0].get("function_name", ""),  # type: ignore[arg-type]
            occurrences=occurrences,
            count=len(occurrences),
        ))

    return DuplicateCodeResult(
        items=sorted(groups, key=lambda g: g.count, reverse=True),
        files_scanned=len(paths) - len(scan_failures),
        scan_failures=scan_failures,
    )
