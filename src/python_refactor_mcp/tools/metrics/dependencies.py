"""Module dependency graph and circular dependency detection using ast."""

from __future__ import annotations

import ast
from pathlib import Path

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import DependencyGraph, ModuleDependency, ScanFailure
from python_refactor_mcp.util.file_filter import python_files


def _is_type_checking_guard(node: ast.expr) -> bool:
    """Return whether *node* is the conventional static-only typing guard."""
    return (
        isinstance(node, ast.Name)
        and node.id == "TYPE_CHECKING"
        or isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "typing"
        and node.attr == "TYPE_CHECKING"
    )


class _ImportCollector(ast.NodeVisitor):
    """Collect imports and whether they execute while the module initializes.

    Imports nested in functions are real architectural dependencies, so they
    remain in ``DependencyGraph.dependencies``. They cannot create an import-
    time cycle, however, and neither can imports guarded by ``TYPE_CHECKING``;
    those edges are excluded from the runtime cycle graph.
    """

    def __init__(self) -> None:
        self.imports: list[tuple[ast.Import | ast.ImportFrom, bool]] = []
        self._deferred_scope_depth = 0
        self._type_checking_depth = 0

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        self.imports.append((node, self._is_runtime_import))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        self.imports.append((node, self._is_runtime_import))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_deferred_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_deferred_scope(node)

    def visit_If(self, node: ast.If) -> None:  # noqa: N802
        self.visit(node.test)
        if _is_type_checking_guard(node.test):
            self._type_checking_depth += 1
            for statement in node.body:
                self.visit(statement)
            self._type_checking_depth -= 1
            for statement in node.orelse:
                self.visit(statement)
            return
        for statement in (*node.body, *node.orelse):
            self.visit(statement)

    @property
    def _is_runtime_import(self) -> bool:
        return self._deferred_scope_depth == 0 and self._type_checking_depth == 0

    def _visit_deferred_scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._deferred_scope_depth += 1
        self.generic_visit(node)
        self._deferred_scope_depth -= 1


def _collect_imports(tree: ast.AST) -> list[tuple[ast.Import | ast.ImportFrom, bool]]:
    collector = _ImportCollector()
    collector.visit(tree)
    return collector.imports


def _import_roots(workspace_root: Path) -> tuple[Path, ...]:
    """Return import roots in Python resolution order for common layouts."""
    roots = [workspace_root / name for name in ("src", "lib")]
    return tuple(root.resolve() for root in (*roots, workspace_root) if root.is_dir())


def _resolve_module_to_file(module_name: str, import_roots: tuple[Path, ...]) -> str | None:
    """Resolve an absolute module name to a file within an import root.

    Source-layout roots precede the workspace root so ``src/pkg/mod.py`` is
    resolved as ``pkg.mod``, not ``src.pkg.mod``.
    """
    if not module_name:
        return None

    parts = module_name.split(".")
    for root in import_roots:
        import_path = root.joinpath(*parts)
        package_path = import_path / "__init__.py"
        if package_path.exists():
            return str(package_path.resolve())
        module_path = import_path.with_suffix(".py")
        if module_path.exists():
            return str(module_path.resolve())
    return None


def _package_parts(source: Path, import_roots: tuple[Path, ...]) -> tuple[str, ...] | None:
    """Return the importing module's package relative to its import root."""
    for root in import_roots:
        try:
            relative = source.resolve().relative_to(root)
        except ValueError:
            continue

        module_parts = relative.with_suffix("").parts
        if not module_parts:
            return ()
        return module_parts[:-1]
    return None


def _source_first_import_roots(source: Path, import_roots: tuple[Path, ...]) -> tuple[Path, ...]:
    """Prioritize the source's own root when resolving a relative import."""
    resolved_source = source.resolve()
    for root in import_roots:
        try:
            resolved_source.relative_to(root)
        except ValueError:
            continue
        return (root, *(candidate for candidate in import_roots if candidate != root))
    return import_roots


def _absolute_from_module(
    node: ast.ImportFrom,
    source: Path,
    import_roots: tuple[Path, ...],
) -> str | None:
    """Resolve an ImportFrom module against the source package context."""
    if node.level == 0:
        return node.module or ""

    package = _package_parts(source, import_roots)
    if package is None or node.level > len(package):
        return None

    parent_hops = node.level - 1
    base = package[: len(package) - parent_hops] if parent_hops else package
    if node.module:
        base = (*base, *node.module.split("."))
    return ".".join(base)


def _from_import_name(node: ast.ImportFrom, alias_name: str) -> str:
    """Preserve the source-level dotted spelling of an imported name."""
    prefix = f"{'.' * node.level}{node.module or ''}"
    separator = "." if node.module else ""
    return f"{prefix}{separator}{alias_name}"


def _resolve_from_target(
    absolute_module: str | None,
    alias_name: str,
    import_roots: tuple[Path, ...],
) -> str | None:
    """Resolve a from-import, preferring an imported child module when present."""
    if absolute_module is None:
        return None

    if alias_name != "*":
        child_module = f"{absolute_module}.{alias_name}" if absolute_module else alias_name
        child_target = _resolve_module_to_file(child_module, import_roots)
        if child_target is not None:
            return child_target
    return _resolve_module_to_file(absolute_module, import_roots)


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Return deterministic strongly connected components that contain cycles."""
    next_index = 0
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def strong_connect(node: str) -> None:
        nonlocal next_index
        indexes[node] = next_index
        lowlinks[node] = next_index
        next_index += 1
        stack.append(node)
        on_stack.add(node)

        for neighbor in sorted(graph.get(node, set())):
            if neighbor not in indexes:
                strong_connect(neighbor)
                lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
            elif neighbor in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[neighbor])

        if lowlinks[node] != indexes[node]:
            return

        component: list[str] = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break

        if len(component) > 1 or node in graph.get(node, set()):
            components.append(sorted(component))

    nodes = set(graph)
    for targets in graph.values():
        nodes.update(targets)
    for node in sorted(nodes):
        if node not in indexes:
            strong_connect(node)

    return sorted(components, key=tuple)


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
        paths = python_files(workspace_root)

    all_deps: list[ModuleDependency] = []
    modules: set[str] = set()
    graph: dict[str, set[str]] = {}
    scan_failures: list[ScanFailure] = []
    import_roots = _import_roots(workspace_root)

    for fp in sorted(paths):
        source = str(fp.resolve())
        modules.add(source)
        try:
            content = fp.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(fp))
        except (SyntaxError, OSError) as exc:
            scan_failures.append(
                ScanFailure(
                    file_path=source,
                    phase="read_or_parse",
                    error_type=type(exc).__name__,
                )
            )
            continue

        if source not in graph:
            graph[source] = set()

        for node, is_runtime_import in _collect_imports(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _resolve_module_to_file(alias.name, import_roots)
                    all_deps.append(ModuleDependency(
                        source=source,
                        target=target or alias.name,
                        import_name=alias.name,
                        line=node.lineno - 1,
                    ))
                    if target:
                        modules.add(target)
                        if is_runtime_import:
                            graph[source].add(target)
            else:
                absolute_module = _absolute_from_module(node, fp, import_roots)
                resolution_roots = (
                    _source_first_import_roots(fp, import_roots) if node.level else import_roots
                )
                for alias in node.names:
                    import_name = _from_import_name(node, alias.name)
                    target = _resolve_from_target(absolute_module, alias.name, resolution_roots)
                    all_deps.append(ModuleDependency(
                        source=source,
                        target=target or absolute_module or import_name,
                        import_name=import_name,
                        line=node.lineno - 1,
                    ))
                    if target:
                        modules.add(target)
                        if is_runtime_import:
                            graph[source].add(target)

    cycles = _find_cycles(graph)
    return DependencyGraph(
        dependencies=all_deps,
        modules=sorted(modules),
        circular_dependencies=cycles,
        scan_failures=scan_failures,
    )
