"""Module dependency graph and circular dependency detection using ast."""

from __future__ import annotations

import ast
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import DependencyGraph, ModuleDependency


def _resolve_module_to_file(module_name: str, workspace_root: Path) -> str | None:
    """Try to resolve a module name to a file path within the workspace."""
    parts = module_name.split(".")
    # Try as package/__init__.py
    package_path = workspace_root / "/".join(parts) / "__init__.py"
    if package_path.exists():
        return str(package_path.resolve())
    # Try as module.py
    module_path = workspace_root / "/".join(parts[:-1]) / (parts[-1] + ".py") if len(parts) > 1 else workspace_root / (parts[0] + ".py")
    if module_path.exists():
        return str(module_path.resolve())
    return None


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Find all circular dependencies via DFS."""
    cycles: list[list[str]] = []
    visited: set[str] = set()
    path: list[str] = []
    path_set: set[str] = set()

    def dfs(node: str) -> None:
        if node in path_set:
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            normalized = tuple(sorted(cycle[:-1]))
            if normalized not in seen_cycles:
                seen_cycles.add(normalized)
                cycles.append(cycle)
            return
        if node in visited:
            return
        visited.add(node)
        path.append(node)
        path_set.add(node)
        for neighbor in graph.get(node, set()):
            dfs(neighbor)
        path.pop()
        path_set.discard(node)

    seen_cycles: set[tuple[str, ...]] = set()
    for node in graph:
        dfs(node)
    return cycles


async def get_module_dependencies(
    config: ServerConfig,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
) -> DependencyGraph:
    """Parse import statements and build a dependency graph with cycle detection."""
    workspace_root = config.workspace_root
    paths: list[Path]
    if file_paths:
        paths = [Path(fp) for fp in file_paths]
    elif file_path:
        paths = [Path(file_path)]
    else:
        paths = list(workspace_root.rglob("*.py"))

    all_deps: list[ModuleDependency] = []
    modules: set[str] = set()
    graph: dict[str, set[str]] = {}

    for fp in paths:
        source = str(fp.resolve())
        modules.add(source)
        try:
            content = fp.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(fp))
        except (SyntaxError, OSError):
            continue

        if source not in graph:
            graph[source] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _resolve_module_to_file(alias.name, workspace_root)
                    all_deps.append(ModuleDependency(
                        source=source,
                        target=target or alias.name,
                        import_name=alias.name,
                        line=node.lineno - 1,
                    ))
                    if target:
                        modules.add(target)
                        graph[source].add(target)
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                target = _resolve_module_to_file(module_name, workspace_root)
                for alias in node.names:
                    all_deps.append(ModuleDependency(
                        source=source,
                        target=target or module_name,
                        import_name=f"{module_name}.{alias.name}" if module_name else alias.name,
                        line=node.lineno - 1,
                    ))
                if target:
                    modules.add(target)
                    graph[source].add(target)

    cycles = _find_cycles(graph)
    return DependencyGraph(
        dependencies=all_deps,
        modules=sorted(modules),
        circular_dependencies=cycles,
    )
