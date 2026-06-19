"""Re-attach parameter type annotations that rope's ``change_signature`` drops.

rope's ``ArgumentNormalizer`` / ``ArgumentAdder`` (used by the ``normalize`` /
``rename`` / ``reorder`` / ``add`` / ``remove`` operations) re-emit the
parameter list without PEP 484/585 annotations. This module runs a LibCST
post-pass on the *definition* file: it reads the annotations off the original
function and fills any annotation rope dropped, matching by parameter name
(robust for every name-preserving op) and, for an all-``rename`` operation set,
by original position.

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


def _annotations_by_name(func: cst.FunctionDef) -> dict[str, cst.Annotation]:
    """Map every parameter name to its annotation node (where present)."""
    out: dict[str, cst.Annotation] = {}
    p = func.params
    candidates: list[cst.Param] = [*p.posonly_params, *p.params, *p.kwonly_params]
    for star in (p.star_arg, p.star_kwarg):
        if isinstance(star, cst.Param):
            candidates.append(star)
    for param in candidates:
        if param.annotation is not None:
            out[param.name.value] = param.annotation
    return out


def _fill(
    params: list[cst.Param],
    by_name: dict[str, cst.Annotation],
    by_pos: list[cst.Annotation | None],
    rename_index: dict[str, int],
) -> tuple[list[cst.Param], bool]:
    """Return params with missing annotations filled, plus a changed flag."""
    changed = False
    out: list[cst.Param] = []
    for param in params:
        if param.annotation is None:
            restored = by_name.get(param.name.value)
            if restored is None and param.name.value in rename_index:
                idx = rename_index[param.name.value]
                if 0 <= idx < len(by_pos):
                    restored = by_pos[idx]
            if restored is not None:
                param = param.with_changes(annotation=restored)
                changed = True
        out.append(param)
    return out, changed


def restore_param_annotations(
    original_src: str,
    new_src: str,
    line: int,
    character: int,
    operations: list[SignatureOperation],
) -> str:
    """Re-attach annotations rope dropped from the target function definition.

    *line* / *character* are the rope (0-based) position of the function name.
    Returns the corrected source, or *new_src* unchanged when nothing could be
    restored (no target def, no dropped annotations, or unparseable input).
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

    by_name = _annotations_by_name(orig_func)
    by_pos = [p.annotation for p in _positional_params(orig_func)]

    # Index-based restore for the renamed parameter is only safe when every
    # operation is a rename (positions are preserved); a reorder/add/remove
    # would shift indices and make the original-position annotation wrong.
    rename_index: dict[str, int] = {}
    if operations and all(op.op == "rename" for op in operations):
        rename_index = {
            op.new_name: op.index
            for op in operations
            if op.new_name is not None and op.index is not None
        }

    params = new_func.params
    posonly, c1 = _fill(list(params.posonly_params), by_name, by_pos, rename_index)
    normal, c2 = _fill(list(params.params), by_name, by_pos, rename_index)
    kwonly, c3 = _fill(list(params.kwonly_params), by_name, by_pos, rename_index)
    star_changes: list[bool] = []
    star_arg = params.star_arg
    if isinstance(star_arg, cst.Param):
        (star_arg,), sc = _fill([star_arg], by_name, by_pos, rename_index)
        star_changes.append(sc)
    star_kwarg = params.star_kwarg
    if isinstance(star_kwarg, cst.Param):
        (star_kwarg,), sc = _fill([star_kwarg], by_name, by_pos, rename_index)
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
