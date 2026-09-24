"""Type-stub generation and source/stub freshness analysis."""

from __future__ import annotations

import ast
import asyncio
import shutil
import sys
import tempfile
import tokenize
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from python_refactor_mcp.errors import PyrightError, ToolInputError
from python_refactor_mcp.models import (
    TypeStubCreationResult,
    TypeStubFreshnessResult,
    TypeStubSignatureDrift,
)
from python_refactor_mcp.util.shared import validate_identifier, validate_workspace_path

if TYPE_CHECKING:
    from python_refactor_mcp.config import ServerConfig

DEFAULT_STUB_DIR = "typings"
"""Workspace-relative stub root; matches Pyright's default ``stubPath``."""

_CREATESTUB_TIMEOUT_SECONDS = 300.0
_UNRESOLVED_IMPORT_MARKER = "could not be resolved"


def _validate_package_name(package_name: str) -> str:
    """Require a dotted import name whose every segment is a valid identifier."""
    if not package_name:
        raise ToolInputError("package_name must be a non-empty import name (parameter: package_name)")
    for segment in package_name.split("."):
        validate_identifier(segment, "package_name")
    return package_name


def _resolve_stub_root(config: ServerConfig, output_dir: str | None) -> Path:
    """Return the workspace-bounded stub root; relative paths anchor at the workspace."""
    workspace_root = config.workspace_root
    if output_dir is None:
        candidate = workspace_root / DEFAULT_STUB_DIR
    else:
        requested = Path(output_dir).expanduser()
        candidate = requested if requested.is_absolute() else workspace_root / requested
    return Path(validate_workspace_path(str(candidate), workspace_root))


async def _run_pyright_createstub(config: ServerConfig, package_name: str, cwd: Path) -> tuple[int, str]:
    """Run ``pyright --createstub`` headlessly in *cwd*; return (exit code, combined output)."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pyright",
        "--createstub",
        package_name,
        "--pythonpath",
        str(config.python_executable),
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout_bytes, _ = await asyncio.wait_for(process.communicate(), timeout=_CREATESTUB_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        process.kill()
        await process.wait()
        raise PyrightError(
            f"pyright --createstub timed out after {_CREATESTUB_TIMEOUT_SECONDS:.0f}s for {package_name!r}"
        ) from exc
    returncode = process.returncode if process.returncode is not None else -1
    return returncode, stdout_bytes.decode("utf-8", errors="replace")


async def create_type_stubs(
    config: ServerConfig,
    package_name: str,
    output_dir: str | None = None,
) -> TypeStubCreationResult:
    """Generate ``.pyi`` stubs for an importable package with the headless Pyright CLI.

    Stubs are written immediately (no preview) to ``<output root>/<top-level package>``,
    where the output root is ``output_dir`` (workspace-relative or absolute, but always
    inside the workspace) or ``<workspace>/typings`` by default. An existing target
    directory is refused rather than merged or overwritten. Pyright resolves the import
    against the workspace interpreter; an unresolvable import, or a run that produces no
    ``.pyi`` files, is an error.
    """
    _validate_package_name(package_name)
    stub_root = _resolve_stub_root(config, output_dir)
    top_level = package_name.split(".", 1)[0]
    target = stub_root / top_level
    if target.exists():
        raise ToolInputError(
            f"Stub target already exists: {target}; remove it or choose another output_dir "
            "(parameters: package_name, output_dir)"
        )

    with tempfile.TemporaryDirectory(prefix="pyright-createstub-") as scratch:
        scratch_root = Path(scratch)
        returncode, output = await _run_pyright_createstub(config, package_name, scratch_root)
        if returncode != 0:
            if _UNRESOLVED_IMPORT_MARKER in output:
                raise ToolInputError(
                    f"Import '{package_name}' could not be resolved by the workspace interpreter "
                    f"{config.python_executable} (parameter: package_name)"
                )
            raise PyrightError(f"pyright --createstub exited {returncode} for {package_name!r}: {output.strip()}")

        generated = scratch_root / DEFAULT_STUB_DIR / top_level
        if not generated.is_dir() or not any(generated.rglob("*.pyi")):
            raise ToolInputError(
                f"Pyright produced no .pyi stubs for '{package_name}' (parameter: package_name)"
            )

        stub_root.mkdir(parents=True, exist_ok=True)
        if target.exists():
            # Re-checked after the subprocess: shutil.move would nest into a directory
            # created meanwhile instead of refusing it.
            raise ToolInputError(f"Stub target already exists: {target} (parameters: package_name, output_dir)")
        await asyncio.to_thread(shutil.move, str(generated), str(target))

    files = sorted(str(path) for path in target.rglob("*.pyi"))
    return TypeStubCreationResult(package_name=package_name, output_dir=str(stub_root), files=files)


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
        raise ToolInputError("source_file must point to a .py file")
    if stub_path.suffix != ".pyi":
        raise ToolInputError("stub_file must point to a .pyi file")
    if not source_path.is_file():
        raise ToolInputError(f"Source file not found: {source_path} (parameter: source_file)")
    if not stub_path.is_file():
        raise ToolInputError(
            f"Stub file not found: {stub_path} (parameter: stub_file; when omitted it defaults to "
            "the .pyi file adjacent to source_file)"
        )

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
