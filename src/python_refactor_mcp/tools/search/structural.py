"""LibCST matcher-based structural search and replace for Python code."""

from __future__ import annotations

import ast
import asyncio
import re
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import libcst as cst
from libcst import matchers as m
from libcst.metadata import CodeRange, MetadataWrapper, PositionProvider

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import (
    Position,
    Range,
    RefactorResult,
    ScanFailure,
    StructuralMatch,
)
from python_refactor_mcp.tools.refactoring.helpers import post_apply_diagnostics
from python_refactor_mcp.util.cst_apply import apply_cst_transformer_batch

from ._helpers import (
    apply_limit_items,
    python_files,
    range_sort_key,
)

if TYPE_CHECKING:
    from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient

# Simplified pattern shortcuts → LibCST matcher DSL translations.
_SIMPLIFIED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^call:(\w+)$", re.IGNORECASE), r"m.Call(func=m.Name('\1'))"),
    (re.compile(r"^attr_call:(\w+)\.(\w+)$", re.IGNORECASE), r"m.Call(func=m.Attribute(attr=m.Name('\2')))"),
    (re.compile(r"^star_import$", re.IGNORECASE), "m.ImportFrom(names=m.ImportStar())"),
    (re.compile(r"^except:(\w+)$", re.IGNORECASE), r"m.ExceptHandler(type=m.Name('\1'))"),
    (re.compile(r"^except$", re.IGNORECASE), "m.ExceptHandler()"),
    (re.compile(r"^decorator:(\w+)$", re.IGNORECASE), r"m.Decorator(decorator=m.Name('\1'))"),
    (re.compile(r"^assert$", re.IGNORECASE), "m.Assert()"),
    (re.compile(r"^global$", re.IGNORECASE), "m.Global()"),
    (re.compile(r"^raise$", re.IGNORECASE), "m.Raise()"),
    (re.compile(r"^yield$", re.IGNORECASE), "m.Yield()"),
]


def _translate_simplified_pattern(pattern: str) -> str | None:
    """Try to translate a simplified shorthand into a LibCST matcher expression.

    Returns the translated pattern string on match, or None if no shorthand applies.
    """
    stripped = pattern.strip()
    for regex, replacement in _SIMPLIFIED_PATTERNS:
        match = regex.match(stripped)
        if match:
            return match.expand(replacement)
    return None


# Only these AST node types may appear in a matcher pattern. A strict positive
# allowlist (not a name denylist) is required: the previous ``ast.Name``-only
# check let attribute/subscript chains on literals reach object internals
# (e.g. ``().__class__.__bases__[0].__subclasses__()``) and execute arbitrary
# code through ``eval``. Subscripts and dunder attributes are the escape
# primitives, so both are rejected outright.
_ALLOWED_PATTERN_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.Call,
    ast.keyword,
    ast.Attribute,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.UnaryOp,
    ast.Invert,  # ~matcher (DoesNotMatch)
    ast.BinOp,
    ast.BitOr,  # matcher | matcher (OneOf)
)
_ALLOWED_PATTERN_NAMES = frozenset({"m", "cst", "True", "False", "None"})


def compile_pattern(pattern: str) -> m.BaseMatcherNode:
    """Translate, validate, and evaluate a LibCST matcher pattern.

    The pattern string is evaluated with ``eval``, so it is first vetted
    against a strict AST node-type allowlist (matcher calls, attribute access
    on ``m``/``cst``, literals, and the ``|``/``~`` matcher operators only).
    Dunder attribute access and subscripts are rejected to close the
    sandbox-escape / arbitrary-code-execution vector. Raises ``ValueError`` on
    any invalid or disallowed pattern.

    Predicate matchers that take a Python callable (e.g. ``m.MatchIfTrue(...)``)
    are intentionally unsupported: a ``lambda`` in the pattern would re-open
    arbitrary code execution, so ``ast.Lambda`` is not on the allowlist.
    """
    translated = _translate_simplified_pattern(pattern)
    effective_pattern = translated if translated is not None else pattern

    try:
        pattern_ast = ast.parse(effective_pattern, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid pattern syntax: {exc}") from exc

    for node in ast.walk(pattern_ast):
        if not isinstance(node, _ALLOWED_PATTERN_NODES):
            raise ValueError(
                f"Pattern uses a disallowed expression ({type(node).__name__}). "
                "Only LibCST matcher calls on 'm'/'cst', literals, and the | and ~ "
                "operators are permitted."
            )
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_PATTERN_NAMES:
            raise ValueError(
                f"Pattern references forbidden name '{node.id}'. "
                "Only 'm' and 'cst' are allowed as top-level names."
            )
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Pattern may not access dunder attributes.")

    try:
        matcher = eval(effective_pattern, {"__builtins__": {}}, {"m": m, "cst": cst})  # noqa: S307
    except Exception as exc:
        raise ValueError(
            "Invalid LibCST matcher pattern. Use matcher syntax, e.g.:\n"
            "  m.Call(func=m.Name('foo'))          — find calls to foo()\n"
            "  m.ExceptHandler(type=m.Name('Exception'))  — find except Exception\n"
            "  m.ImportFrom(names=m.ImportStar())  — find star imports\n"
            "  m.Assert()                          — find assert statements"
        ) from exc
    if not isinstance(matcher, m.BaseMatcherNode):
        raise ValueError("Pattern must evaluate to a LibCST matcher node.")
    return matcher


async def structural_search(
    config: ServerConfig,
    pattern: str,
    file_path: str | None = None,
    language: str = "python",
    limit: int | None = None,
) -> tuple[list[StructuralMatch], int, list[ScanFailure]]:
    """Run LibCST matcher-based structural search for Python code."""
    if language.strip().lower() != "python":
        raise ValueError("Only language='python' is supported.")

    matcher = compile_pattern(pattern)

    candidate_files = [Path(file_path).resolve()] if file_path is not None else python_files(config.workspace_root)

    def _scan_file(path: Path) -> list[StructuralMatch]:
        source = path.read_text(encoding="utf-8")
        module = cst.parse_module(source)
        wrapper = MetadataWrapper(module)

        class _Collector(cst.CSTVisitor):
            METADATA_DEPENDENCIES = (PositionProvider,)

            def __init__(self) -> None:
                self.matches: list[StructuralMatch] = []

            def on_visit(self, node: cst.CSTNode) -> bool:
                if not m.matches(node, matcher):
                    return True
                code_range = self.get_metadata(PositionProvider, node)
                if not isinstance(code_range, CodeRange):
                    return True
                self.matches.append(
                    StructuralMatch(
                        file_path=str(path.resolve()),
                        range=Range(
                            start=Position(
                                line=code_range.start.line - 1,
                                character=code_range.start.column,
                            ),
                            end=Position(
                                line=code_range.end.line - 1,
                                character=code_range.end.column,
                            ),
                        ),
                        matched_text=module.code_for_node(node),
                    )
                )
                return True

        collector = _Collector()
        wrapper.visit(collector)
        return collector.matches

    all_results = await asyncio.gather(
        *[asyncio.to_thread(_scan_file, path) for path in candidate_files],
        return_exceptions=True,
    )
    files_scanned = sum(1 for r in all_results if isinstance(r, list))
    scan_failures = [
        ScanFailure(
            file_path=str(path.resolve()),
            phase="read_or_parse",
            error_type=type(result).__name__,
        )
        for path, result in zip(candidate_files, all_results, strict=True)
        if isinstance(result, BaseException)
    ]
    flattened = [item for result in all_results if isinstance(result, list) for item in result]
    sorted_items = sorted(flattened, key=lambda item: (item.file_path, *range_sort_key(item.range)))
    return apply_limit_items(sorted_items, limit), files_scanned, scan_failures


# ── structural_replace ───────────────────────────────────────────────────

_CAPTURE_REF = re.compile(r"\$(\w+)")
_EMPTY_MODULE = cst.Module([])


def _render_capture(value: cst.CSTNode | Sequence[cst.CSTNode]) -> str:
    """Render a captured node (or node sequence) back to source text.

    Sequence captures (e.g. an argument list) are normalized: each element's
    own trailing comma — which ``code_for_node`` includes — is stripped and the
    pieces are rejoined with ``, ``.
    """
    def _one(node: cst.CSTNode) -> str:
        # ``code_for_node`` on an ``Arg`` includes its trailing comma/whitespace;
        # strip it so the rendered piece is a clean expression fragment.
        return _EMPTY_MODULE.code_for_node(node).strip().rstrip(",").strip()

    if isinstance(value, cst.CSTNode):
        return _one(value)
    return ", ".join(_one(node) for node in value)


def _render_replacement(template: str, extracted: dict[str, cst.CSTNode | Sequence[cst.CSTNode]]) -> str:
    """Substitute ``$name`` placeholders in *template* with captured source.

    Single regex pass (prefix-safe: ``$x`` never matches inside ``$xy``).
    Unknown captures and captures spanning a comment raise ``BackendError``.
    """

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in extracted:
            raise BackendError(f"replacement references unknown capture '${name}'")
        rendered = _render_capture(extracted[name])
        if "#" in rendered:
            raise BackendError(f"capture '${name}' spans a comment, which is not supported")
        return rendered

    return _CAPTURE_REF.sub(_sub, template)


class _StructuralReplacer(cst.CSTTransformer):
    """Rewrite every match of *matcher* using the ``$name`` *template*.

    Runs ``matchers.replace`` once over the module (it replaces the outermost
    match and does not recurse into its own output, so there is no double
    rewrite). Only expression-position matches are supported; a statement-
    position match raises rather than emitting an invalid tree.
    """

    def __init__(self, matcher: m.BaseMatcherNode, template: str) -> None:
        self._matcher = matcher
        self._template = template
        self.count = 0

    def _replace(
        self, node: cst.CSTNode, extracted: dict[str, cst.CSTNode | Sequence[cst.CSTNode]]
    ) -> cst.BaseExpression:
        if not isinstance(node, cst.BaseExpression):
            raise BackendError(
                "structural_replace supports expression-position matches only; "
                f"pattern matched a {type(node).__name__}."
            )
        rendered = _render_replacement(self._template, extracted)
        try:
            new_node = cst.parse_expression(rendered)
        except cst.ParserSyntaxError as exc:
            raise BackendError(f"replacement '{rendered}' is not a valid expression: {exc}") from exc
        self.count += 1
        return new_node

    def leave_Module(self, original_node: cst.Module, updated_node: cst.Module) -> cst.Module:
        # ``matchers.replace`` accepts the replacement only via ``inspect.isfunction``,
        # which is False for bound methods — so delegate through a local function.
        def _replacement(
            node: cst.CSTNode, extracted: dict[str, cst.CSTNode | Sequence[cst.CSTNode]]
        ) -> cst.BaseExpression:
            return self._replace(node, extracted)

        result = m.replace(updated_node, self._matcher, _replacement)
        assert isinstance(result, cst.Module)
        return result


async def structural_replace(
    pyright: PyrightLSPClient,
    pattern: str,
    replacement: str,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Rewrite structural matches of *pattern* using the *replacement* template.

    *pattern* is a LibCST matcher expression (same DSL as ``structural_search``);
    capture sub-nodes with ``m.SaveMatchedNode(<matcher>, "name")`` and refer to
    them in *replacement* as ``$name``. Expression-position matches only.
    Defaults to preview mode; ``apply=True`` writes atomically and refreshes
    Pyright diagnostics.
    """
    matcher = compile_pattern(pattern)

    targets: list[str] = list(file_paths) if file_paths else []
    if file_path is not None:
        targets.append(file_path)
    if not targets:
        return RefactorResult(
            edits=[], files_affected=[], description="No files provided to scan", applied=False
        )

    transformers: list[_StructuralReplacer] = []

    def _factory(_file_path: str) -> cst.CSTTransformer:
        transformer = _StructuralReplacer(matcher, replacement)
        transformers.append(transformer)
        return transformer

    edits, files_affected = apply_cst_transformer_batch(targets, _factory, apply=apply)
    rewrites = sum(transformer.count for transformer in transformers)
    if not edits:
        return RefactorResult(
            edits=[], files_affected=[], description="No matches for the pattern", applied=False
        )

    description = f"Rewrote {rewrites} match(es) across {len(files_affected)} file(s)"
    result = RefactorResult(edits=edits, files_affected=files_affected, description=description, applied=apply)
    if apply:
        return await post_apply_diagnostics(pyright, result)
    return result
