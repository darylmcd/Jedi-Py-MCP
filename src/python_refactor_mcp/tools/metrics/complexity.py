"""Cyclomatic and cognitive complexity metrics using stdlib ast."""

from __future__ import annotations

import ast

from python_refactor_mcp.models import CodeMetricsResult, FunctionMetrics, ScanFailure
from python_refactor_mcp.util.scan import parse_python_file


def _cyclomatic_complexity(node: ast.AST) -> int:
    """Count decision points for cyclomatic complexity (McCabe)."""
    count = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler, ast.Assert)):
            count += 1
        elif isinstance(child, ast.BoolOp):
            count += len(child.values) - 1
    return count


def _cognitive_complexity(node: ast.AST, depth: int = 0) -> int:
    """Estimate cognitive complexity (nesting-aware)."""
    total = 0
    for child in ast.iter_child_nodes(node):
        increment = 0
        nesting_increment = 0
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler)):
            increment = 1
            nesting_increment = depth
        elif isinstance(child, ast.BoolOp):
            increment = 1
        total += increment + nesting_increment
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler)):
            total += _cognitive_complexity(child, depth + 1)
        else:
            total += _cognitive_complexity(child, depth)
    return total


def _max_nesting_depth(node: ast.AST, current: int = 0) -> int:
    """Calculate maximum nesting depth."""
    max_depth = current
    for child in ast.iter_child_nodes(node):
        _nesting_types = (ast.If, ast.While, ast.For, ast.AsyncFor, ast.With, ast.AsyncWith, ast.Try, ast.ExceptHandler)
        if isinstance(child, _nesting_types):
            max_depth = max(max_depth, _max_nesting_depth(child, current + 1))
        else:
            max_depth = max(max_depth, _max_nesting_depth(child, current))
    return max_depth


def _function_loc(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count lines of code in a function."""
    if not node.body:
        return 1
    return node.end_lineno - node.lineno + 1 if node.end_lineno else 1


async def code_metrics(
    file_path: str,
    file_paths: list[str] | None = None,
) -> CodeMetricsResult:
    """Compute cyclomatic/cognitive complexity, nesting depth, LoC, and param count."""
    paths = [file_path] if file_paths is None else file_paths
    all_functions: list[FunctionMetrics] = []
    scan_failures: list[ScanFailure] = []

    for fp in paths:
        parsed, failure = parse_python_file(fp)
        if parsed is None:
            if failure is not None:
                scan_failures.append(failure)
            continue

        for node in ast.walk(parsed.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = _cyclomatic_complexity(node)
                cog = _cognitive_complexity(node)
                depth = _max_nesting_depth(node)
                loc = _function_loc(node)
                params = len(node.args.args) + len(node.args.posonlyargs) + len(node.args.kwonlyargs)
                if node.args.vararg:
                    params += 1
                if node.args.kwarg:
                    params += 1
                all_functions.append(FunctionMetrics(
                    name=node.name,
                    file_path=str(parsed.path),
                    line=node.lineno - 1,
                    cyclomatic_complexity=cc,
                    cognitive_complexity=cog,
                    nesting_depth=depth,
                    loc=loc,
                    parameter_count=params,
                ))

    total = len(all_functions)
    avg_cc = sum(f.cyclomatic_complexity for f in all_functions) / total if total else 0.0
    max_cc = max((f.cyclomatic_complexity for f in all_functions), default=0)

    return CodeMetricsResult(
        functions=all_functions,
        total_functions=total,
        avg_cyclomatic=round(avg_cc, 2),
        max_cyclomatic=max_cc,
        files_scanned=len(paths) - len(scan_failures),
        scan_failures=scan_failures,
    )
