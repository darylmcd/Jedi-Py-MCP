"""LibCST matcher-based structural search for Python code."""

from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path

import libcst as cst
from libcst import matchers as m
from libcst.metadata import CodeRange, MetadataWrapper, PositionProvider

from python_refactor_mcp.config import ServerConfig
from python_refactor_mcp.models import (
    Position,
    Range,
    StructuralMatch,
)

from ._helpers import (
    _apply_limit,
    _python_files,
    _range_sort_key,
)

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


async def structural_search(
    config: ServerConfig,
    pattern: str,
    file_path: str | None = None,
    language: str = "python",
    limit: int | None = None,
) -> list[StructuralMatch]:
    """Run LibCST matcher-based structural search for Python code."""
    if language.strip().lower() != "python":
        raise ValueError("Only language='python' is supported.")

    # Try simplified pattern shorthand first.
    translated = _translate_simplified_pattern(pattern)
    effective_pattern = translated if translated is not None else pattern

    # Validate pattern AST before eval to prevent sandbox escape via attribute chains.
    try:
        pattern_ast = ast.parse(effective_pattern, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid pattern syntax: {exc}") from exc
    _ALLOWED_NAMES = {"m", "cst", "True", "False", "None"}
    for node in ast.walk(pattern_ast):
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_NAMES:
            raise ValueError(
                f"Pattern references forbidden name '{node.id}'. "
                "Only 'm' and 'cst' are allowed as top-level names."
            )

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

    candidate_files = [Path(file_path).resolve()] if file_path is not None else _python_files(config.workspace_root)

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
    flattened = [item for result in all_results if isinstance(result, list) for item in result]
    sorted_items = sorted(flattened, key=lambda item: (item.file_path, *_range_sort_key(item.range)))
    return _apply_limit(sorted_items, limit)
