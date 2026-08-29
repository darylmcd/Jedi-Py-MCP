"""Re-attach signature metadata that rope's ``change_signature`` drops.

rope's ``ArgumentNormalizer`` / ``ArgumentAdder`` (used by the ``normalize`` /
``rename`` / ``reorder`` / ``add`` / ``remove`` operations) re-emit the
parameter list without PEP 484/585 annotations or, in some operations, default
values. This module runs a LibCST post-pass on the *definition* file and tracks
parameter provenance through ordered add/remove/reorder/rename operations.

It never overwrites an annotation rope kept (idempotent), and on any parse
failure it returns the rope output unchanged — so it can only improve, never
regress, the result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import libcst as cst
from libcst.metadata import CodeRange, MetadataWrapper, PositionProvider

if TYPE_CHECKING:
    from python_refactor_mcp.models import SignatureOperation


class _FuncFinder(cst.CSTVisitor):
    """Collect the ``FunctionDef`` whose name node covers a (line, column)."""

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, line_1based: int, column: int) -> None:
        self._line = line_1based
        self._column = column
        self.found: cst.FunctionDef | None = None

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        if self.found is not None:
            return
        code_range = self.get_metadata(PositionProvider, node.name)
        if not isinstance(code_range, CodeRange):
            return
        start, end = code_range.start, code_range.end
        if start.line == self._line and start.column <= self._column <= end.column:
            self.found = node


def _find_funcdef_at(module: cst.Module, line: int, character: int) -> cst.FunctionDef | None:
    """Find the ``FunctionDef`` whose name is at the rope (0-based) position."""
    finder = _FuncFinder(line + 1, character)  # PositionProvider lines are 1-based.
    # ``unsafe_skip_copy`` keeps the visited nodes identity-equal to those in
    # *module* so the caller's ``deep_replace`` can find the matched def. Safe:
    # the finder only reads metadata, it never mutates during traversal.
    MetadataWrapper(module, unsafe_skip_copy=True).visit(finder)
    return finder.found


def _positional_params(func: cst.FunctionDef) -> list[cst.Param]:
    """Positional parameters in declaration order (posonly + normal)."""
    return [*func.params.posonly_params, *func.params.params]


def _params_by_name(func: cst.FunctionDef) -> dict[str, cst.Param]:
    """Map every original parameter name to its CST node."""
    out: dict[str, cst.Param] = {}
    p = func.params
    candidates: list[cst.Param] = [*p.posonly_params, *p.params, *p.kwonly_params]
    for star in (p.star_arg, p.star_kwarg):
        if isinstance(star, cst.Param):
            candidates.append(star)
    for param in candidates:
        out[param.name.value] = param
    return out


def _positional_provenance(
    func: cst.FunctionDef,
    operations: list[SignatureOperation],
) -> tuple[dict[str, cst.Param], dict[str, cst.BaseExpression]]:
    """Resolve final positional names to original params and requested defaults."""
    original = _positional_params(func)
    # (original index, current name, explicit default, default intentionally removed)
    state: list[tuple[int | None, str, str | None, bool]] = [
        (index, param.name.value, None, False) for index, param in enumerate(original)
    ]

    for operation in operations:
        if operation.op == "reorder" and operation.new_order is not None:
            if len(operation.new_order) == len(state) and all(
                0 <= index < len(state) for index in operation.new_order
            ):
                state = [state[index] for index in operation.new_order]
        elif operation.op == "rename" and operation.index is not None and operation.new_name:
            if 0 <= operation.index < len(state):
                origin, _name, _explicit, blocked = state[operation.index]
                state[operation.index] = (origin, operation.new_name, operation.default, blocked)
        elif operation.op == "add" and operation.index is not None and operation.name:
            if 0 <= operation.index <= len(state):
                state.insert(operation.index, (None, operation.name, operation.default, False))
        elif operation.op == "remove" and operation.index is not None:
            if 0 <= operation.index < len(state):
                state.pop(operation.index)
        elif (
            operation.op == "inline_default"
            and operation.index is not None
            and 0 <= operation.index < len(state)
        ):
            origin, name, explicit, _blocked = state[operation.index]
            state[operation.index] = (origin, name, explicit, True)

    sources: dict[str, cst.Param] = {}
    defaults: dict[str, cst.BaseExpression] = {}
    for origin, name, explicit_default, default_blocked in state:
        source = original[origin] if origin is not None and 0 <= origin < len(original) else None
        if source is not None:
            sources[name] = source
        if default_blocked:
            continue
        if explicit_default is not None:
            try:
                defaults[name] = cst.parse_expression(explicit_default)
            except cst.ParserSyntaxError:
                continue
        elif source is not None and source.default is not None:
            defaults[name] = source.default
    return sources, defaults


def _fill(
    params: list[cst.Param],
    sources: dict[str, cst.Param],
    defaults: dict[str, cst.BaseExpression],
) -> tuple[list[cst.Param], bool]:
    """Return params with missing annotations/defaults filled, plus a flag."""
    changed = False
    out: list[cst.Param] = []
    for param in params:
        name = param.name.value
        source = sources.get(name)
        annotation = param.annotation
        default = param.default
        if annotation is None and source is not None and source.annotation is not None:
            annotation = source.annotation
            changed = True
        if default is None and name in defaults:
            default = defaults[name]
            changed = True
        if annotation is not param.annotation or default is not param.default:
            changes: dict[str, object] = {"annotation": annotation, "default": default}
            if annotation is not None and default is not None:
                # PEP 8: an annotated parameter with a default uses ' = '.
                changes["equal"] = cst.AssignEqual(
                    whitespace_before=cst.SimpleWhitespace(" "),
                    whitespace_after=cst.SimpleWhitespace(" "),
                )
            param = param.with_changes(**changes)
        out.append(param)
    return out, changed


def restore_signature_metadata(
    original_src: str,
    new_src: str,
    line: int,
    character: int,
    operations: list[SignatureOperation],
) -> str:
    """Re-attach annotations/defaults rope dropped from the target definition.

    *line* / *character* are the rope (0-based) position of the function name.
    Returns the corrected source, or *new_src* unchanged when nothing could be
    restored (no target def, no dropped metadata, or unparseable input).
    """
    try:
        orig_module = cst.parse_module(original_src)
        new_module = cst.parse_module(new_src)
    except cst.ParserSyntaxError:
        return new_src

    orig_func = _find_funcdef_at(orig_module, line, character)
    new_func = _find_funcdef_at(new_module, line, character)
    if orig_func is None or new_func is None or orig_func.name.value != new_func.name.value:
        return new_src

    by_name = _params_by_name(orig_func)
    positional_sources, positional_defaults = _positional_provenance(orig_func, operations)
    defaults_by_name = {
        name: param.default for name, param in by_name.items() if param.default is not None
    }
    defaults_by_name.update(positional_defaults)

    params = new_func.params
    posonly, c1 = _fill(list(params.posonly_params), positional_sources, positional_defaults)
    normal, c2 = _fill(list(params.params), positional_sources, positional_defaults)
    kwonly, c3 = _fill(list(params.kwonly_params), by_name, defaults_by_name)
    star_changes: list[bool] = []
    star_arg = params.star_arg
    if isinstance(star_arg, cst.Param):
        (star_arg,), sc = _fill([star_arg], by_name, defaults_by_name)
        star_changes.append(sc)
    star_kwarg = params.star_kwarg
    if isinstance(star_kwarg, cst.Param):
        (star_kwarg,), sc = _fill([star_kwarg], by_name, defaults_by_name)
        star_changes.append(sc)

    returns = new_func.returns
    returns_changed = False
    if new_func.returns is None and orig_func.returns is not None:
        returns = orig_func.returns
        returns_changed = True

    if not (c1 or c2 or c3 or any(star_changes) or returns_changed):
        return new_src

    corrected = new_func.with_changes(
        params=params.with_changes(
            posonly_params=posonly,
            params=normal,
            kwonly_params=kwonly,
            star_arg=star_arg,
            star_kwarg=star_kwarg,
        ),
        returns=returns,
    )
    result_module = new_module.deep_replace(new_func, corrected)
    assert isinstance(result_module, cst.Module)
    return result_module.code
