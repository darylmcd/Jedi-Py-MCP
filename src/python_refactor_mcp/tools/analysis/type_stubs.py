"""Type-stub generation and source/stub freshness analysis."""

from __future__ import annotations

import ast
import tokenize
from collections import defaultdict
from pathlib import Path
from typing import Protocol

from python_refactor_mcp.models import TypeStubFreshnessResult, TypeStubSignatureDrift


class _PyrightStubBackend(Protocol):
    """Protocol describing the Pyright method needed for stub generation."""

    async def create_type_stub(self, package_name: str, output_dir: str | None = None) -> bool: ...


async def create_type_stubs(
    pyright: _PyrightStubBackend,
    package_name: str,
    output_dir: str | None = None,
) -> bool:
    """Generate .pyi stub files for a third-party package lacking type information."""
    return await pyright.create_type_stub(package_name, output_dir)


_FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _qualified_name(expression: ast.expr) -> str | None:
    """Return the dotted name for a decorator/base expression when static."""
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        parent = _qualified_name(expression.value)
        return f"{parent}.{expression.attr}" if parent else expression.attr
    if isinstance(expression, ast.Call):
        return _qualified_name(expression.func)
    return None


def _is_public_api_name(name: str) -> bool:
    """Include public names and language-defined dunder methods, not private helpers."""
    return not name.startswith("_") or (name.startswith("__") and name.endswith("__"))


def _has_decorator(node: _FunctionNode, name: str) -> bool:
    return any((_qualified_name(item) or "").rsplit(".", 1)[-1] == name for item in node.decorator_list)


def _is_protocol(node: ast.ClassDef) -> bool:
    return any((_qualified_name(base) or "").rsplit(".", 1)[-1] == "Protocol" for base in node.bases)


def _render_parameter(name: str, optional: bool) -> str:
    return f"{name}=?" if optional else name


def _render_signature(node: _FunctionNode) -> str:
    """Render the caller-visible signature shape while ignoring annotation spelling.

    Stub annotations are commonly richer than runtime annotations. Comparing their
    text would create churn, so freshness is about calling convention: asyncness,
    binding, parameter kinds/names, and required-vs-optional state.
    """
    args = node.args
    positional = [*args.posonlyargs, *args.args]
    required_count = len(positional) - len(args.defaults)
    pieces: list[str] = []

    for index, _argument in enumerate(args.posonlyargs):
        pieces.append(_render_parameter(f"pos{index}", index >= required_count))
    if args.posonlyargs:
        pieces.append("/")

    positional_offset = len(args.posonlyargs)
    for index, argument in enumerate(args.args, start=positional_offset):
        pieces.append(_render_parameter(argument.arg, index >= required_count))

    if args.vararg is not None:
        pieces.append("*args")
    elif args.kwonlyargs:
        pieces.append("*")

    for argument, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        pieces.append(_render_parameter(argument.arg, default is not None))
    if args.kwarg is not None:
        pieces.append("**kwargs")

    binding = ""
    if _has_decorator(node, "classmethod"):
        binding = "classmethod "
    elif _has_decorator(node, "staticmethod"):
        binding = "staticmethod "
    async_prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"{binding}{async_prefix}({', '.join(pieces)})"


def _collect_signatures(
    tree: ast.Module,
) -> tuple[dict[str, str], set[str], set[str]]:
    """Collect public top-level functions and methods plus conservative skips."""
    nodes_by_symbol: defaultdict[str, list[_FunctionNode]] = defaultdict(list)
    protocols: set[str] = set()

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_public_api_name(node.name):
                nodes_by_symbol[node.name].append(node)
            continue
        if not isinstance(node, ast.ClassDef) or not _is_public_api_name(node.name):
            continue
        if _is_protocol(node):
            protocols.add(node.name)
            continue
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_public_api_name(child.name):
                nodes_by_symbol[f"{node.name}.{child.name}"].append(child)

    overloads = {
        symbol
        for symbol, nodes in nodes_by_symbol.items()
        if any(_has_decorator(node, "overload") for node in nodes)
    }
    signatures = {
        symbol: _render_signature(nodes[-1])
        for symbol, nodes in nodes_by_symbol.items()
        if symbol not in overloads
    }
    return signatures, overloads, protocols


def _parse_module(path: Path) -> ast.Module:
    with tokenize.open(path) as stream:
        return ast.parse(stream.read(), filename=str(path))


def check_type_stub_freshness(
    source_file: str,
    stub_file: str | None = None,
) -> TypeStubFreshnessResult:
    """Compare the callable API shape of a ``.py`` source and ``.pyi`` stub.

    Overloaded callables and Protocol classes are reported as conservative skips:
    their stub signatures intentionally need not mirror one runtime definition.
    """
    source_path = Path(source_file).expanduser().resolve()
    stub_path = Path(stub_file).expanduser().resolve() if stub_file else source_path.with_suffix(".pyi")
    if source_path.suffix != ".py":
        raise ValueError("source_file must point to a .py file")
    if stub_path.suffix != ".pyi":
        raise ValueError("stub_file must point to a .pyi file")
    if not source_path.is_file():
        raise FileNotFoundError(f"Source file does not exist: {source_path}")
    if not stub_path.is_file():
        raise FileNotFoundError(f"Stub file does not exist: {stub_path}")

    source_signatures, source_overloads, source_protocols = _collect_signatures(_parse_module(source_path))
    stub_signatures, stub_overloads, stub_protocols = _collect_signatures(_parse_module(stub_path))

    skipped_overloads = source_overloads | stub_overloads
    skipped_protocols = source_protocols | stub_protocols
    for symbol in skipped_overloads:
        source_signatures.pop(symbol, None)
        stub_signatures.pop(symbol, None)
    for protocol in skipped_protocols:
        prefix = f"{protocol}."
        source_signatures = {
            symbol: signature for symbol, signature in source_signatures.items() if not symbol.startswith(prefix)
        }
        stub_signatures = {
            symbol: signature for symbol, signature in stub_signatures.items() if not symbol.startswith(prefix)
        }

    source_symbols = set(source_signatures)
    stub_symbols = set(stub_signatures)
    mismatches = [
        TypeStubSignatureDrift(
            symbol=symbol,
            implementation_signature=source_signatures[symbol],
            stub_signature=stub_signatures[symbol],
        )
        for symbol in sorted(source_symbols & stub_symbols)
        if source_signatures[symbol] != stub_signatures[symbol]
    ]
    missing_in_stub = sorted(source_symbols - stub_symbols)
    missing_in_source = sorted(stub_symbols - source_symbols)
    return TypeStubFreshnessResult(
        source_file=str(source_path),
        stub_file=str(stub_path),
        fresh=not (missing_in_stub or missing_in_source or mismatches),
        missing_in_stub=missing_in_stub,
        missing_in_source=missing_in_source,
        signature_mismatches=mismatches,
        skipped_overloads=sorted(skipped_overloads),
        skipped_protocols=sorted(skipped_protocols),
    )
