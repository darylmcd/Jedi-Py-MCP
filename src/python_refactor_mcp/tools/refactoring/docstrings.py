"""Synchronize function parameters with structured docstring fields.

The transformer deliberately limits itself to parameter sections in existing
function docstrings. It preserves prose and existing parameter descriptions,
adds missing entries, removes stale entries, and orders the result to match the
signature. Google, NumPy, and Sphinx layouts are supported; ambiguous layouts
fail closed instead of mixing conventions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import libcst as cst
from libcst.metadata import CodeRange, MetadataWrapper, PositionProvider

from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient
from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import Position, Range, RefactorResult, TextEdit
from python_refactor_mcp.util.cst_apply import parse_module
from python_refactor_mcp.util.diff import write_atomic_if_unchanged
from python_refactor_mcp.util.shared import end_position_for_content

from .helpers import post_apply_diagnostics

_STYLES = frozenset({"auto", "google", "numpy", "sphinx"})
_GOOGLE_HEADER = re.compile(r"^(?P<indent>\s*)(?:Args|Arguments|Parameters):\s*$")
_GOOGLE_ENTRY = re.compile(
    r"^(?P<indent>\s+)(?P<name>\*{0,2}[A-Za-z_]\w*)"
    r"(?P<suffix>\s*(?:\([^)]*\))?\s*:.*)$"
)
_SECTION_HEADER = re.compile(r"^(?P<indent>\s*)[A-Za-z][A-Za-z ]*:\s*$")
_NUMPY_HEADER = re.compile(r"^(?P<indent>\s*)Parameters\s*$")
_NUMPY_ENTRY = re.compile(
    r"^(?P<indent>\s+)(?P<name>\*{0,2}[A-Za-z_]\w*)(?P<suffix>\s*:\s*.+)$"
)
_SPHINX_PARAM = re.compile(
    r"^(?P<indent>\s*):param(?:\s+.+?)?\s+(?P<name>\*{0,2}[A-Za-z_]\w*)"
    r"(?P<suffix>\s*:.*)$"
)
_SPHINX_TYPE = re.compile(
    r"^(?P<indent>\s*):type\s+(?P<name>\*{0,2}[A-Za-z_]\w*)(?P<suffix>\s*:.*)$"
)
_SPHINX_FIELD = re.compile(r"^\s*:[A-Za-z_][\w-]*(?:\s+[^:]*)?:")


@dataclass(frozen=True, slots=True)
class _Parameter:
    """One signature parameter and its preferred docstring rendering."""

    name: str
    display_name: str
    annotation: str | None


@dataclass(frozen=True, slots=True)
class _LineBlock:
    """A contiguous docstring field owned by one parameter."""

    start: int
    end: int
    lines: tuple[str, ...]


class _FunctionAtPosition(cst.CSTVisitor):
    """Find the function whose name covers one zero-based source position."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, line: int, character: int) -> None:
        self._line = line + 1
        self._character = character
        self.found: cst.FunctionDef | None = None

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:  # noqa: N802
        if self.found is not None:
            return
        code_range = self.get_metadata(PositionProvider, node.name)
        if not isinstance(code_range, CodeRange):
            return
        if (
            code_range.start.line == self._line
            and code_range.start.column <= self._character <= code_range.end.column
        ):
            self.found = node


def _function_docstring(function: cst.FunctionDef) -> cst.SimpleString:
    if not isinstance(function.body, cst.IndentedBlock) or not function.body.body:
        raise BackendError("docstring_sync requires a multiline function body")
    first = function.body.body[0]
    if not isinstance(first, cst.SimpleStatementLine) or len(first.body) != 1:
        raise BackendError("Target function has no simple string docstring")
    expression = first.body[0]
    if not isinstance(expression, cst.Expr) or not isinstance(expression.value, cst.SimpleString):
        raise BackendError("Target function has no simple string docstring")
    return expression.value


def _parameter(
    module: cst.Module,
    param: cst.Param,
    *,
    prefix: str = "",
) -> _Parameter:
    annotation = None
    if param.annotation is not None:
        annotation = " ".join(module.code_for_node(param.annotation.annotation).split())
    return _Parameter(
        name=param.name.value,
        display_name=f"{prefix}{param.name.value}",
        annotation=annotation,
    )


def _parameters(module: cst.Module, function: cst.FunctionDef) -> list[_Parameter]:
    params = function.params
    positional = [*params.posonly_params, *params.params]
    if positional and positional[0].name.value in {"self", "cls"}:
        positional = positional[1:]

    result = [_parameter(module, param) for param in positional]
    if isinstance(params.star_arg, cst.Param):
        result.append(_parameter(module, params.star_arg, prefix="*"))
    result.extend(_parameter(module, param) for param in params.kwonly_params)
    if params.star_kwarg is not None:
        result.append(_parameter(module, params.star_kwarg, prefix="**"))
    return result


def _normalized_name(value: str) -> str:
    return value.lstrip("*")


def _detect_style(lines: list[str]) -> str | None:
    detected: set[str] = set()
    if any(_GOOGLE_HEADER.match(line) for line in lines):
        detected.add("google")
    if any(
        _NUMPY_HEADER.match(line) and index + 1 < len(lines) and re.fullmatch(r"\s*-{3,}\s*", lines[index + 1])
        for index, line in enumerate(lines)
    ):
        detected.add("numpy")
    if any(_SPHINX_PARAM.match(line) for line in lines):
        detected.add("sphinx")

    if len(detected) > 1:
        raise BackendError(f"Ambiguous docstring styles: {sorted(detected)!r}")
    return next(iter(detected), None)


def _selected_style(lines: list[str], requested: str) -> str:
    normalized = requested.strip().lower()
    if normalized not in _STYLES:
        raise BackendError(f"Invalid docstring style {requested!r}; expected one of: {sorted(_STYLES)!r}")
    detected = _detect_style(lines)
    if normalized == "auto":
        if detected is None:
            raise BackendError("Cannot auto-detect docstring style; pass google, numpy, or sphinx")
        return detected
    if detected is not None and detected != normalized:
        raise BackendError(f"Requested {normalized} style conflicts with detected {detected} style")
    return normalized


def _section_end(lines: list[str], start: int, header_indent: int) -> int:
    for index in range(start, len(lines)):
        match = _SECTION_HEADER.match(lines[index])
        if match is not None and len(match.group("indent")) <= header_indent:
            return index
    return len(lines)


def _numpy_section_end(lines: list[str], start: int, header_indent: int) -> int:
    for index in range(start, len(lines) - 1):
        if not lines[index].strip() or not re.fullmatch(r"\s*-{3,}\s*", lines[index + 1]):
            continue
        indent = len(lines[index]) - len(lines[index].lstrip())
        if indent <= header_indent:
            return index
    return len(lines)


def _blocks_for_entries(
    lines: list[str],
    start: int,
    end: int,
    pattern: re.Pattern[str],
) -> tuple[list[str], dict[str, _LineBlock], str]:
    matches = [(index, match) for index in range(start, end) if (match := pattern.match(lines[index]))]
    if not matches:
        return (lines[start:end], {}, "    ")

    blocks: dict[str, _LineBlock] = {}
    for match_index, (line_index, match) in enumerate(matches):
        name = _normalized_name(match.group("name"))
        if name in blocks:
            raise BackendError(f"Docstring contains duplicate parameter entry {name!r}")
        block_end = matches[match_index + 1][0] if match_index + 1 < len(matches) else end
        blocks[name] = _LineBlock(line_index, block_end, tuple(lines[line_index:block_end]))
    first_index, first_match = matches[0]
    return (lines[start:first_index], blocks, first_match.group("indent"))


def _replace_entry_name(line: str, pattern: re.Pattern[str], display_name: str) -> str:
    match = pattern.match(line)
    if match is None:
        raise BackendError("Internal docstring field mismatch")
    return f'{line[: match.start("name")]}{display_name}{line[match.end("name") :]}'


def _with_section_spacing(body: list[str], *, has_following_section: bool) -> list[str]:
    while len(body) > 1 and not body[-1].strip() and not body[-2].strip():
        body.pop()
    if has_following_section and (not body or body[-1].strip()):
        body.append("")
    return body


def _append_section(lines: list[str], section: list[str]) -> list[str]:
    result = list(lines)
    if result and result[-1].strip():
        result.append("")
    result.extend(section)
    return result


def _sync_google(lines: list[str], parameters: list[_Parameter]) -> list[str]:
    header = next(((index, match) for index, line in enumerate(lines) if (match := _GOOGLE_HEADER.match(line))), None)
    if header is None:
        entries = [
            f"    {param.display_name}{f' ({param.annotation})' if param.annotation else ''}:"
            for param in parameters
        ]
        return _append_section(lines, ["Args:", *entries])

    header_index, header_match = header
    end = _section_end(lines, header_index + 1, len(header_match.group("indent")))
    prelude, blocks, entry_indent = _blocks_for_entries(lines, header_index + 1, end, _GOOGLE_ENTRY)
    rendered = [lines[header_index], *prelude]
    for param in parameters:
        block = blocks.get(param.name)
        if block is None:
            annotation = f" ({param.annotation})" if param.annotation else ""
            rendered.append(f"{entry_indent}{param.display_name}{annotation}:")
            continue
        rendered.append(_replace_entry_name(block.lines[0], _GOOGLE_ENTRY, param.display_name))
        rendered.extend(block.lines[1:])
    rendered = _with_section_spacing(rendered, has_following_section=end < len(lines))
    return [*lines[:header_index], *rendered, *lines[end:]]


def _sync_numpy(lines: list[str], parameters: list[_Parameter]) -> list[str]:
    header = next(
        (
            (index, match)
            for index, line in enumerate(lines)
            if (match := _NUMPY_HEADER.match(line))
            and index + 1 < len(lines)
            and re.fullmatch(r"\s*-{3,}\s*", lines[index + 1])
        ),
        None,
    )
    if header is None:
        entries = [
            f"{param.display_name} : {param.annotation or 'Any'}"
            for param in parameters
        ]
        return _append_section(lines, ["Parameters", "----------", *entries])

    header_index, header_match = header
    start = header_index + 2
    end = _numpy_section_end(lines, start, len(header_match.group("indent")))
    if any(
        "," in line and re.match(r"^\s+\*{0,2}[A-Za-z_]\w*\s*,", line)
        for line in lines[start:end]
    ):
        raise BackendError("NumPy multi-parameter entries are ambiguous; split them before syncing")
    prelude, blocks, entry_indent = _blocks_for_entries(lines, start, end, _NUMPY_ENTRY)
    rendered = [lines[header_index], lines[header_index + 1], *prelude]
    for param in parameters:
        block = blocks.get(param.name)
        if block is None:
            rendered.append(f"{entry_indent}{param.display_name} : {param.annotation or 'Any'}")
            continue
        rendered.append(_replace_entry_name(block.lines[0], _NUMPY_ENTRY, param.display_name))
        rendered.extend(block.lines[1:])
    rendered = _with_section_spacing(rendered, has_following_section=end < len(lines))
    return [*lines[:header_index], *rendered, *lines[end:]]


def _directive_blocks(lines: list[str], pattern: re.Pattern[str]) -> dict[str, _LineBlock]:
    matches = [(index, match) for index, line in enumerate(lines) if (match := pattern.match(line))]
    blocks: dict[str, _LineBlock] = {}
    for line_index, match in matches:
        name = _normalized_name(match.group("name"))
        if name in blocks:
            raise BackendError(f"Docstring contains duplicate parameter directive {name!r}")
        end = line_index + 1
        while end < len(lines) and not _SPHINX_FIELD.match(lines[end]):
            end += 1
        blocks[name] = _LineBlock(line_index, end, tuple(lines[line_index:end]))
    return blocks


def _sync_sphinx(lines: list[str], parameters: list[_Parameter]) -> list[str]:
    param_blocks = _directive_blocks(lines, _SPHINX_PARAM)
    type_blocks = _directive_blocks(lines, _SPHINX_TYPE)
    removed: set[int] = set()
    for block in (*param_blocks.values(), *type_blocks.values()):
        removed.update(range(block.start, block.end))

    if removed:
        insertion = min(removed)
        sample = min((*param_blocks.values(), *type_blocks.values()), key=lambda block: block.start)
        match = _SPHINX_PARAM.match(sample.lines[0]) or _SPHINX_TYPE.match(sample.lines[0])
        assert match is not None
        indent = match.group("indent")
    else:
        insertion = next((index for index, line in enumerate(lines) if _SPHINX_FIELD.match(line)), len(lines))
        indent = ""

    rendered: list[str] = []
    for param in parameters:
        param_block = param_blocks.get(param.name)
        if param_block is None:
            rendered.append(f"{indent}:param {param.display_name}:")
        else:
            rendered.append(_replace_entry_name(param_block.lines[0], _SPHINX_PARAM, param.display_name))
            rendered.extend(param_block.lines[1:])

        type_block = type_blocks.get(param.name)
        if type_block is not None:
            rendered.append(_replace_entry_name(type_block.lines[0], _SPHINX_TYPE, param.name))
            rendered.extend(type_block.lines[1:])
        elif param.annotation is not None:
            rendered.append(f"{indent}:type {param.name}: {param.annotation}")

    result: list[str] = []
    inserted = False
    for index, line in enumerate(lines):
        if index == insertion:
            if result and result[-1].strip() and rendered:
                result.append("")
            result.extend(rendered)
            if index < len(lines) and lines[index].strip() and rendered:
                result.append("")
            inserted = True
        if index not in removed:
            result.append(line)
    if not inserted:
        result = _append_section(result, rendered)
    return result


def _render_literal(original: cst.SimpleString, content: str) -> cst.SimpleString:
    prefix = original.prefix
    if prefix.lower() not in {"", "u"}:
        raise BackendError("docstring_sync does not rewrite raw, byte, or formatted string docstrings")
    quote_char = original.quote[0]
    quote = quote_char * 3
    escaped = content.replace("\\", "\\\\").replace(quote, f"\\{quote}")
    try:
        replacement = cst.parse_expression(f"{prefix}{quote}{escaped}{quote}")
    except cst.ParserSyntaxError as exc:
        raise BackendError("Cannot safely encode the synchronized docstring") from exc
    if not isinstance(replacement, cst.SimpleString) or replacement.evaluated_value != content:
        raise BackendError("Cannot safely preserve the synchronized docstring value")
    return replacement


async def docstring_sync(
    pyright: PyrightLSPClient,
    file_path: str,
    line: int,
    character: int,
    style: str = "auto",
    apply: bool = False,
) -> RefactorResult:
    """Synchronize a function signature with its docstring parameter fields.

    ``line`` and ``character`` must point at the function name. Existing
    descriptions are preserved. Missing parameters are added without invented
    prose, stale parameters are removed, and entries are reordered to match the
    signature. Defaults to preview mode.
    """
    try:
        original_bytes = Path(file_path).read_bytes()
        source = original_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except (FileNotFoundError, OSError, UnicodeError) as exc:
        raise BackendError(f"Cannot read file for docstring synchronization: {exc}") from exc

    module = parse_module(source, file_path)
    finder = _FunctionAtPosition(line, character)
    MetadataWrapper(module, unsafe_skip_copy=True).visit(finder)
    if finder.found is None:
        raise BackendError("No function name found at the requested position")

    original_docstring = _function_docstring(finder.found)
    content = original_docstring.evaluated_value
    if not isinstance(content, str):
        raise BackendError("Target docstring is not a text string")
    lines = content.splitlines()
    trailing_newline = content.endswith("\n")
    parameters = _parameters(module, finder.found)
    selected = _selected_style(lines, style)
    if selected == "google":
        synchronized = _sync_google(lines, parameters)
    elif selected == "numpy":
        synchronized = _sync_numpy(lines, parameters)
    else:
        synchronized = _sync_sphinx(lines, parameters)

    new_content = "\n".join(synchronized) + ("\n" if trailing_newline else "")
    replacement = _render_literal(original_docstring, new_content)
    new_module = module.deep_replace(original_docstring, replacement)
    assert isinstance(new_module, cst.Module)
    new_source = new_module.code

    edits: list[TextEdit] = []
    files_affected: list[str] = []
    if new_source != source:
        edits.append(
            TextEdit(
                file_path=file_path,
                range=Range(
                    start=Position(line=0, character=0),
                    end=end_position_for_content(source),
                ),
                new_text=new_source,
            )
        )
        files_affected.append(file_path)
        if apply:
            write_atomic_if_unchanged(file_path, new_source, original_bytes)

    result = RefactorResult(
        edits=edits,
        files_affected=files_affected,
        description=f"Synchronized {len(parameters)} parameter(s) in a {selected}-style docstring",
        applied=bool(apply and edits),
    )
    if apply and edits:
        return await post_apply_diagnostics(pyright, result)
    return result


__all__ = ["docstring_sync"]
