"""Architecture analysis: coupling metrics and layer violation detection."""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path
from typing import Any

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    CouplingMetrics,
    DependencyGraph,
    InterfaceComparison,
    LayerViolation,
    ProtocolSource,
)


async def get_coupling_metrics(
    config: ServerConfig,
    dependency_graph: DependencyGraph | None = None,
    file_paths: list[str] | None = None,
) -> list[CouplingMetrics]:
    """Compute afferent/efferent coupling and instability per module.

    Ca = number of modules that import this module (afferent).
    Ce = number of modules this module imports (efferent).
    Instability I = Ce / (Ca + Ce), range [0, 1].
    """
    # Build adjacency from the dependency graph
    if dependency_graph is None:
        from python_refactor_mcp.tools.metrics.dependencies import get_module_dependencies
        dependency_graph = await get_module_dependencies(config, file_paths=file_paths)

    efferent: dict[str, set[str]] = defaultdict(set)
    afferent: dict[str, set[str]] = defaultdict(set)

    for dep in dependency_graph.dependencies:
        if dep.target in dependency_graph.modules:
            efferent[dep.source].add(dep.target)
            afferent[dep.target].add(dep.source)

    results: list[CouplingMetrics] = []
    for module in dependency_graph.modules:
        ca = len(afferent.get(module, set()))
        ce = len(efferent.get(module, set()))
        instability = ce / (ca + ce) if (ca + ce) > 0 else 0.0
        results.append(CouplingMetrics(
            module=module,
            afferent_coupling=ca,
            efferent_coupling=ce,
            instability=round(instability, 3),
        ))

    return sorted(results, key=lambda m: m.instability, reverse=True)


async def check_layer_violations(
    config: ServerConfig,
    layers: list[list[str]],
    file_paths: list[str] | None = None,
) -> list[LayerViolation]:
    """Check import directions against declared layer ordering.

    ``layers`` is ordered from highest to lowest layer.
    layers[0] is the top layer (e.g., presentation), layers[-1] is the bottom (e.g., domain).
    Imports from lower layers to higher layers are violations.
    """
    workspace_root = config.workspace_root
    # Build layer index: module_pattern -> layer_number
    layer_index: dict[str, int] = {}
    for layer_num, patterns in enumerate(layers):
        for pattern in patterns:
            layer_index[pattern] = layer_num

    def _get_layer(module_path: str) -> int | None:
        """Find the layer number for a module path or name.

        Uses path-component matching to avoid false positives from stdlib
        or third-party modules whose names happen to contain a layer keyword.
        """
        # Split into path parts for component-level matching.
        parts = Path(module_path).parts if "/" in module_path or "\\" in module_path else module_path.split(".")
        for pattern, layer_num in layer_index.items():
            if pattern in parts:
                return layer_num
        return None

    violations: list[LayerViolation] = []
    if file_paths:
        paths = [Path(fp) for fp in file_paths]
    else:
        from python_refactor_mcp.util.file_filter import python_files  # noqa: PLC0415
        paths = python_files(workspace_root)

    for fp in paths:
        try:
            content = fp.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(fp))
        except (SyntaxError, OSError):
            continue

        source_str = str(fp.resolve())
        source_layer = _get_layer(source_str)
        if source_layer is None:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            target_name: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target_name = alias.name
            else:
                target_name = node.module

            if target_name is None:
                continue

            target_layer = _get_layer(target_name)
            if target_layer is None:
                continue

            # Violation: lower layer (higher index) importing from higher layer (lower index)
            if source_layer > target_layer:
                violations.append(LayerViolation(
                    source_module=source_str,
                    target_module=target_name,
                    source_layer=source_layer,
                    target_layer=target_layer,
                    import_line=node.lineno - 1,
                ))

    return violations


def _extract_methods(tree: ast.Module, class_name: str) -> dict[str, dict[str, object]]:
    """Extract method signatures from a class in an AST."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            methods: dict[str, dict[str, object]] = {}
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    params = []
                    for arg in item.args.args:
                        if arg.arg not in ("self", "cls"):
                            params.append(arg.arg)
                    ret = ast.unparse(item.returns) if item.returns else None
                    methods[item.name] = {"params": params, "return_annotation": ret}
            return methods
    return {}


async def interface_conformance(
    file_path: str,
    class_names: list[str],
) -> InterfaceComparison:
    """Compare class interfaces to detect implicit protocol conformance."""
    content = Path(file_path).read_text(encoding="utf-8")
    tree = ast.parse(content, filename=file_path)

    class_methods: dict[str, dict[str, dict[str, object]]] = {}
    for cls_name in class_names:
        class_methods[cls_name] = _extract_methods(tree, cls_name)

    # Find common and unique methods
    all_method_sets = [set(m.keys()) for m in class_methods.values()]
    if not all_method_sets:
        return InterfaceComparison(classes=class_names, common_methods=[], unique_methods={}, signature_mismatches=[])

    common = set.intersection(*all_method_sets) if all_method_sets else set()
    unique: dict[str, list[str]] = {}
    for cls_name, methods in class_methods.items():
        unique_methods = set(methods.keys()) - common
        if unique_methods:
            unique[cls_name] = sorted(unique_methods)

    # Check signature mismatches in common methods
    mismatches: list[dict[str, object]] = []
    for method_name in sorted(common):
        signatures = {cls: class_methods[cls][method_name] for cls in class_names if method_name in class_methods[cls]}
        param_lists: list[tuple[Any, ...]] = []
        for sig in signatures.values():
            raw = sig.get("params")
            if isinstance(raw, list):
                param_lists.append(tuple(raw))
        if len(set(param_lists)) > 1:
            mismatches.append({
                "method": method_name,
                "signatures": {cls: sig["params"] for cls, sig in signatures.items()},
            })

    return InterfaceComparison(
        classes=class_names,
        common_methods=sorted(common),
        unique_methods=unique,
        signature_mismatches=mismatches,
    )


async def extract_protocol(
    file_path: str,
    class_names: list[str],
    protocol_name: str = "GeneratedProtocol",
) -> ProtocolSource:
    """Generate a Protocol class from common methods of given classes."""
    comparison = await interface_conformance(file_path, class_names)

    content = Path(file_path).read_text(encoding="utf-8")
    tree = ast.parse(content, filename=file_path)

    # Get method details from the first class that has them
    lines = [f"class {protocol_name}(Protocol):"]
    if not comparison.common_methods:
        lines.append("    pass")
    else:
        first_class = class_names[0]
        methods = _extract_methods(tree, first_class)
        for method_name in comparison.common_methods:
            if method_name.startswith("_") and method_name != "__init__":
                continue
            sig = methods.get(method_name, {})
            params_raw = sig.get("params", [])
            params_list = params_raw if isinstance(params_raw, list) else []
            ret = sig.get("return_annotation")
            param_str = ", ".join(["self"] + [str(p) for p in params_list])
            ret_str = f" -> {ret}" if ret else ""
            lines.append(f"    def {method_name}({param_str}){ret_str}: ...")

    source_code = "\n".join(lines) + "\n"
    return ProtocolSource(
        protocol_name=protocol_name,
        source_code=source_code,
        methods=comparison.common_methods,
    )
