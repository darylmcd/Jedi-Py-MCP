"""Type annotation coverage analysis using stdlib ast."""

from __future__ import annotations

import ast

from python_refactor_mcp.models import ScanFailure, TypeCoverageReport
from python_refactor_mcp.util.scan import parse_python_file


async def get_type_coverage(
    file_path: str,
    file_paths: list[str] | None = None,
) -> TypeCoverageReport:
    """Report type annotation completeness for function parameters and return types."""
    paths = [file_path] if file_paths is None else file_paths

    total_functions = 0
    annotated_return = 0
    annotated_params = 0
    total_params = 0
    unannotated: list[dict[str, object]] = []
    scan_failures: list[ScanFailure] = []

    for fp in paths:
        parsed, failure = parse_python_file(fp)
        if parsed is None:
            if failure is not None:
                scan_failures.append(failure)
            continue

        resolved = str(parsed.path)
        for node in ast.walk(parsed.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            total_functions += 1

            # Check return annotation
            has_return = node.returns is not None
            if has_return:
                annotated_return += 1

            # Check parameter annotations (skip 'self' and 'cls')
            all_args = node.args.args + node.args.posonlyargs + node.args.kwonlyargs
            skip_first = node.args.args and node.args.args[0].arg in ("self", "cls")
            params_to_check = all_args[1:] if skip_first else all_args

            func_total = len(params_to_check)
            func_annotated = sum(1 for arg in params_to_check if arg.annotation is not None)
            total_params += func_total
            annotated_params += func_annotated

            missing_parts: list[str] = []
            if not has_return:
                missing_parts.append("return")
            missing_param_names = [arg.arg for arg in params_to_check if arg.annotation is None]
            if missing_param_names:
                missing_parts.append(f"params: {', '.join(missing_param_names)}")

            if missing_parts:
                unannotated.append({
                    "file_path": resolved,
                    "function": node.name,
                    "line": node.lineno - 1,
                    "missing": missing_parts,
                })

    return_pct = (annotated_return / total_functions * 100) if total_functions else 100.0
    param_pct = (annotated_params / total_params * 100) if total_params else 100.0

    return TypeCoverageReport(
        file_path=file_path if len(paths) == 1 else None,
        total_functions=total_functions,
        annotated_return=annotated_return,
        annotated_params=annotated_params,
        total_params=total_params,
        return_coverage_pct=round(return_pct, 1),
        param_coverage_pct=round(param_pct, 1),
        unannotated=unannotated,
        files_scanned=len(paths) - len(scan_failures),
        scan_failures=scan_failures,
    )
