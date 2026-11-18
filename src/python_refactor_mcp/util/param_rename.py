"""Rename a function's parameters in its body, proven by compiled-code equivalence.

rope's ``change_signature`` rewrites the definition header and the call sites but
never the function body. :func:`rename_parameter_bindings` renames the body
bindings of the renamed parameters in rope's output and refuses
(``ToolInputError``) whenever it cannot prove the result equivalent.

Design: a small AST *generator* proposes which ``Name`` spans refer to the
parameter; CPython's own compiler is the *oracle*. The probe (the output with
the original parameter names restored) and the result are both ``compile()``d
and their code-object trees are compared instruction by instruction: names may
differ only as the requested old-to-new renames, only for the parameter's
variable (and the free-variable aliases of it in nested code). A wrong proposal
therefore changes an opcode, a free-variable set, ``co_names`` or a constant and
is refused; it can never produce a wrong rewrite. There is no partial rename and
no silent exit: every path returns a verified text or raises.
"""

from __future__ import annotations

import ast
import dis
import types
import warnings
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence

from python_refactor_mcp.errors import ToolInputError
from python_refactor_mcp.util.shared import validate_identifier

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)

# Names whose use reads local variables by name at run time; a rename cannot follow them.
_DYNAMIC_NAMES = frozenset(
    {"locals", "vars", "eval", "exec", "dir", "_getframe", "currentframe", "getargvalues", "stack"}
)
_DYNAMIC_ATTRS = _DYNAMIC_NAMES | {"f_locals"}

# ``ast`` fields that carry an identifier which binds or refers to a variable.
BINDING_FIELDS: dict[type[ast.AST], tuple[str, ...]] = {
    ast.Name: ("id",),
    ast.arg: ("arg",),
    ast.FunctionDef: ("name",),
    ast.AsyncFunctionDef: ("name",),
    ast.ClassDef: ("name",),
    ast.ExceptHandler: ("name",),
    ast.MatchAs: ("name",),
    ast.MatchStar: ("name",),
    ast.MatchMapping: ("rest",),
    ast.TypeVar: ("name",),
    ast.ParamSpec: ("name",),
    ast.TypeVarTuple: ("name",),
    ast.alias: ("name", "asname"),
    ast.Global: ("names",),
    ast.Nonlocal: ("names",),
}

def _refuse(reason: str) -> ToolInputError:
    return ToolInputError(f"cannot rename the parameter consistently: {reason} (parameter: operations)")


def function_ordinal(source: str, lineno: int, name: str) -> int:
    """Index of the function definition at *lineno* named *name* among all definitions, in ``ast.walk`` order."""
    tree = _parse(source)
    for ordinal, node in enumerate(_function_nodes(tree)):
        if node.lineno == lineno and node.name == name:
            return ordinal
    raise _refuse(f"function {name!r} not found at line {lineno}")


def _parse(source: str) -> ast.Module:
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError, RecursionError) as exc:
        raise _refuse(
            f"the source does not parse ({exc}); rope cannot re-emit keyword-only parameters, "
            "and a byte-order mark or other invalid text is not supported"
        ) from exc


def _function_nodes(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [node for node in ast.walk(tree) if isinstance(node, _FUNCTIONS)]


def _param_nodes(args: ast.arguments) -> list[ast.arg]:
    nodes = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    if args.vararg:
        nodes.append(args.vararg)
    if args.kwarg:
        nodes.append(args.kwarg)
    return nodes


def _store_names(target: ast.AST) -> Iterable[str]:
    for node in ast.walk(target):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            yield node.id


def _outer_parts(node: ast.AST) -> list[ast.AST]:
    """Parts of a nested scope that are evaluated in the enclosing scope (decorators, defaults, bases)."""
    parts: list[ast.AST] = []
    if isinstance(node, ast.ClassDef):
        parts += [*node.decorator_list, *node.bases, *(k.value for k in node.keywords)]
    elif isinstance(node, ast.Lambda):
        parts += [*node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)]
    elif isinstance(node, _FUNCTIONS):
        parts += [*node.decorator_list, *node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)]
    return parts


def _own_binding_kinds(nodes: Iterable[ast.AST], old: str) -> set[str]:
    """Binding forms of *old* in the scope owning *nodes*; nested scope bodies are not entered."""
    kinds: set[str] = set()
    stack = list(nodes)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Name):
            if node.id == old and isinstance(node.ctx, (ast.Store, ast.Del)):
                kinds.add("name")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if any((a.asname or a.name.split(".")[0]) == old for a in node.names):
                kinds.add("import")
        elif isinstance(node, ast.ExceptHandler) and node.name == old:
            kinds.add("except")
        elif (isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == old) or (
            isinstance(node, ast.MatchMapping) and node.rest == old
        ):
            kinds.add("match")
        elif isinstance(node, ast.Global) and old in node.names:
            kinds.add("global")
        elif isinstance(node, ast.Nonlocal) and old in node.names:
            kinds.add("nonlocal")
        if isinstance(node, (*_FUNCTIONS, ast.ClassDef)):
            if node.name == old:
                kinds.add("def")
            if any(_type_param_name(tp) == old for tp in node.type_params):
                kinds.add("typeparam")
            stack.extend(_outer_parts(node))
            continue
        if isinstance(node, ast.Lambda):
            stack.extend(_outer_parts(node))
            continue
        if isinstance(node, _COMPREHENSIONS):
            stack.append(node.generators[0].iter)
            # A walrus inside a comprehension binds in the enclosing scope (PEP 572).
            for sub in ast.walk(node):
                if isinstance(sub, ast.NamedExpr) and sub.target.id == old:
                    kinds.add("name")
            continue
        stack.extend(ast.iter_child_nodes(node))
    return kinds


def _type_param_name(param: ast.AST) -> str:
    return str(getattr(param, "name", ""))


def _has_future_annotations(tree: ast.Module) -> bool:
    return any(
        isinstance(stmt, ast.ImportFrom)
        and stmt.module == "__future__"
        and any(alias.name == "annotations" for alias in stmt.names)
        for stmt in tree.body
    )


class ParameterCollector:
    """Collect the ``Name`` nodes that refer to the parameter *old*; refuse unsupported forms."""

    def __init__(self, old: str, new_names: frozenset[str], *, stringified_annotations: bool) -> None:
        self.old = old
        self.new_names = new_names
        self.stringified = stringified_annotations
        self.targets: list[ast.Name] = []

    def visit_all(self, nodes: Iterable[ast.AST], active: bool) -> None:
        for node in nodes:
            self.visit(node, active)

    def visit(self, node: ast.AST, active: bool) -> None:
        if isinstance(node, ast.Name):
            if node.id in _DYNAMIC_NAMES and isinstance(node.ctx, ast.Load):
                raise _refuse(f"{node.id} reads local variables by name")
            if node.id in self.new_names:
                raise _refuse(f"the new name {node.id!r} is already used in the function")
            if node.id == self.old and active:
                self.targets.append(node)
            return
        if isinstance(node, ast.Attribute) and node.attr in _DYNAMIC_ATTRS:
            raise _refuse(f"{node.attr} reads local variables by name")
        if isinstance(node, _NESTED_SCOPES):
            self._scope(node, active)
            return
        if isinstance(node, _COMPREHENSIONS):
            self._comprehension(node, active)
            return
        self._check_identifier_fields(node)
        for child in ast.iter_child_nodes(node):
            self.visit(child, active)

    def _check_identifier_fields(self, node: ast.AST) -> None:
        for cls, fields in BINDING_FIELDS.items():
            if type(node) is not cls:
                continue
            for field in fields:
                value = getattr(node, field)
                for text in value if isinstance(value, list) else [value]:
                    if text and (text in self.new_names or text.split(".")[0] in self.new_names):
                        raise _refuse(f"the new name {text!r} is already used in the function")

    def _scope(self, node: ast.AST, active: bool) -> None:
        old = self.old
        outer = _outer_parts(node)
        params: list[str] = []
        body: list[ast.AST]
        if isinstance(node, ast.Lambda):
            params = [a.arg for a in _param_nodes(node.args)]
            body = [node.body]
        else:
            assert isinstance(node, (*_FUNCTIONS, ast.ClassDef))
            if node.name in self.new_names:
                raise _refuse(f"the new name {node.name!r} is already used in the function")
            body = list(node.body)
            if isinstance(node, _FUNCTIONS):
                params = [a.arg for a in _param_nodes(node.args)]
                if not self.stringified:
                    outer += [a.annotation for a in _param_nodes(node.args) if a.annotation is not None]
                    if node.returns is not None:
                        outer.append(node.returns)
            for tp in node.type_params:
                name = _type_param_name(tp)
                if name == old or name in self.new_names:
                    raise _refuse("a type parameter has the name of a renamed parameter")
                outer.extend(ast.iter_child_nodes(tp))
        if any(p in self.new_names for p in params):
            raise _refuse("a nested function parameter has the new name")
        self.visit_all(outer, active)
        kinds = _own_binding_kinds(body, old)
        if "nonlocal" in kinds and active:
            raise _refuse("a nested scope declares the parameter nonlocal")
        shadowed = old in params or bool(kinds - {"nonlocal"})
        self.visit_all(body, active and not shadowed)

    def _comprehension(self, node: ast.expr, active: bool) -> None:
        assert isinstance(node, _COMPREHENSIONS)
        self.visit(node.generators[0].iter, active)
        binds_old = False
        for gen in node.generators:
            for name in _store_names(gen.target):
                binds_old = binds_old or name == self.old
                if name in self.new_names:
                    raise _refuse(f"the new name {name!r} is a comprehension variable")
        inner = active and not binds_old
        for index, gen in enumerate(node.generators):
            self.visit(gen.target, inner)
            if index:
                self.visit(gen.iter, inner)
            self.visit_all(gen.ifs, inner)
        if isinstance(node, ast.DictComp):
            self.visit(node.key, inner)
            self.visit(node.value, inner)
        else:
            self.visit(node.elt, inner)


def require_other_definitions_untouched(original: str, rewritten: str, ordinal: int) -> None:
    """Refuse when rope also rewrote the signature of another definition with the target's name.

    rope rewrites every definition occurrence it resolves to the target (a
    redefinition, a conditional ``def``, an ``@overload`` stub, a property
    setter) with the target's header, whatever the other definition declared;
    only the target's own definition is meant to change. Parameters are compared
    with ``ast.dump``, which includes annotations: rope drops them, so a
    same-named annotated definition is refused even when its parameters are
    unchanged. A definition rope left alone (a same-named method of an unrelated
    class) is not refused. *ordinal* locates the target (see :func:`function_ordinal`).

    Raises:
        ToolInputError: another definition of the same name was rewritten, or the
            rewritten module does not parse.
    """
    before = _function_nodes(_parse(original))
    try:
        after = _function_nodes(ast.parse(rewritten))
    # Python 3.14 raises SyntaxError for invalid text (a null byte included) and RecursionError for source
    # nested too deeply; ValueError is not raised for ``str`` input.
    except (SyntaxError, RecursionError) as exc:
        raise ToolInputError(
            f"change_signature cannot rewrite this definition: rope produced source that does not parse ({exc}) "
            "(parameter: line)"
        ) from exc
    if len(before) != len(after):
        raise ToolInputError(
            "change_signature cannot rewrite this definition: rope changed the number of function definitions "
            "(parameter: line)"
        )
    name = before[ordinal].name
    for index, (old, new) in enumerate(zip(before, after, strict=True)):
        if index != ordinal and old.name == name and ast.dump(old.args) != ast.dump(new.args):
            raise ToolInputError(
                "change_signature cannot rewrite this definition: rope also rewrote the signature of another "
                f"definition named {name!r} (line {old.lineno}) and would leave its body inconsistent "
                "(parameter: line)"
            )


def _line_starts(data: bytes) -> list[int]:
    starts = [0]
    for line in data.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def _splice(source: str, edits: Sequence[tuple[ast.Name | ast.arg, str]]) -> str:
    """Replace identifier spans (UTF-8 byte offsets, as ``ast`` reports them), highest offset first."""
    data = source.encode("utf-8")
    starts = _line_starts(data)
    spans: list[tuple[int, int, str]] = []
    for node, text in edits:
        begin = starts[node.lineno - 1] + node.col_offset
        if isinstance(node, ast.arg):
            end = begin + len(node.arg.encode("utf-8"))
        else:
            if node.end_lineno != node.lineno or node.end_col_offset is None:
                raise _refuse("an identifier spans several lines")
            end = starts[node.lineno - 1] + node.end_col_offset
        spans.append((begin, end, text))
    for begin, end, text in sorted(spans, reverse=True):
        data = data[:begin] + text.encode("utf-8") + data[end:]
    return data.decode("utf-8")


def _compile(source: str) -> types.CodeType:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            # dont_inherit: this module's own ``from __future__`` flags must not leak in.
            return compile(source, "<rename>", "exec", dont_inherit=True)
        except (SyntaxError, ValueError, RecursionError) as exc:
            raise _refuse(f"the rewritten function does not compile ({exc})") from exc


class NamePairing:
    """Pairing rules for variable names between the probe and the result."""

    def __init__(self, renames: Mapping[str, str]) -> None:
        self.renames = renames
        self.new_names = frozenset(renames.values())

    def name_ok(self, old: str, new: str, *, in_target: bool, free: frozenset[str]) -> bool:
        """Names pair when equal, or when ``renames[old] == new`` for the parameter's own variable."""
        if old == new:
            return True
        return self.renames.get(old) == new and (in_target or old in free)

    def multiset_ok(
        self, probe: Iterable[str], result: Iterable[str], *, in_target: bool, free: frozenset[str]
    ) -> bool:
        """Equal name multisets modulo the renames (CPython sorts cell/free names, so order is not stable)."""
        want, got = Counter(probe), Counter(result)
        for name in set(want) | set(got):
            if name in self.new_names and name not in want:
                continue  # accounted for through its old name below
            target = self.renames.get(name)
            if target is not None and (in_target or name in free):
                if want[name] != got[name] + got[target]:
                    return False
            elif want[name] != got[name]:
                return False
        return True


def _names_of(instruction: dis.Instruction) -> tuple[str, ...]:
    value = instruction.argval
    return tuple(value) if isinstance(value, tuple) else (value,)


def _is_variable_op(instruction: dis.Instruction) -> bool:
    return instruction.opcode in dis.haslocal or instruction.opcode in dis.hasfree


def _group(instructions: list[dis.Instruction]) -> list[list[dis.Instruction]]:
    """Group order-unstable runs: consecutive ``MAKE_CELL`` and the loads feeding a closure tuple."""
    groups: list[list[dis.Instruction]] = []
    index = 0
    while index < len(instructions):
        current = instructions[index]
        if current.opname == "MAKE_CELL":
            end = index
            while end < len(instructions) and instructions[end].opname == "MAKE_CELL":
                end += 1
            groups.append(instructions[index:end])
            index = end
            continue
        if current.opname.startswith("LOAD_") and _is_variable_op(current):
            end = index
            count = 0
            while (
                end < len(instructions)
                and instructions[end].opname.startswith("LOAD_")
                and _is_variable_op(instructions[end])
            ):
                count += len(_names_of(instructions[end]))
                end += 1
            closure_tuple = (
                end + 1 < len(instructions)
                and instructions[end].opname == "BUILD_TUPLE"
                and instructions[end].argval == count
                and isinstance(instructions[end + 1].argval, types.CodeType)
            )
            if closure_tuple:
                groups.append(instructions[index:end])
                index = end
                continue
        groups.append([current])
        index += 1
    return groups


def _compare_code(
    probe: types.CodeType, result: types.CodeType, pair: NamePairing, target: tuple[str, int], path: str
) -> None:
    in_target = (probe.co_name, probe.co_firstlineno) == target
    where = f"{path}/{probe.co_name}"
    free = frozenset(probe.co_freevars)

    def differs(what: str) -> ToolInputError:
        return _refuse(f"the rewritten code differs from the original in {what} of {where}")

    for attr in (
        "co_name",
        "co_qualname",
        "co_flags",
        "co_argcount",
        "co_posonlyargcount",
        "co_kwonlyargcount",
        "co_nlocals",
        "co_names",
        "co_exceptiontable",
    ):
        if getattr(probe, attr) != getattr(result, attr):
            raise differs(attr)
    if len(probe.co_varnames) != len(result.co_varnames) or not all(
        pair.name_ok(x, y, in_target=in_target, free=frozenset())
        for x, y in zip(probe.co_varnames, result.co_varnames, strict=True)
    ):
        raise differs("local variable names")
    if not pair.multiset_ok(probe.co_cellvars, result.co_cellvars, in_target=in_target, free=frozenset()):
        raise differs("cell variables")
    if not pair.multiset_ok(probe.co_freevars, result.co_freevars, in_target=False, free=free):
        raise differs("free variables")
    _compare_instructions(probe, result, pair, in_target, free, differs)
    if len(probe.co_consts) != len(result.co_consts):
        raise differs("constants")
    for left, right in zip(probe.co_consts, result.co_consts, strict=True):
        if isinstance(left, types.CodeType) and isinstance(right, types.CodeType):
            _compare_code(left, right, pair, target, where)
        elif type(left) is not type(right) or repr(left) != repr(right):
            raise differs(f"constant {left!r}")


def _compare_instructions(
    probe: types.CodeType,
    result: types.CodeType,
    pair: NamePairing,
    in_target: bool,
    free: frozenset[str],
    differs: Callable[[str], ToolInputError],
) -> None:
    left_groups = _group(list(dis.get_instructions(probe)))
    right_groups = _group(list(dis.get_instructions(result)))
    if len(left_groups) != len(right_groups):
        raise differs("instruction count")
    for left, right in zip(left_groups, right_groups, strict=True):
        if len(left) != len(right) or left[0].offset != right[0].offset:
            raise differs("instruction layout")
        if len(left) > 1:  # an order-unstable run: compare as multisets
            same_ops = sorted(i.opname for i in left) == sorted(i.opname for i in right)
            left_names = [n for i in left for n in _names_of(i)]
            right_names = [n for i in right for n in _names_of(i)]
            if not same_ops or not pair.multiset_ok(left_names, right_names, in_target=in_target, free=free):
                raise differs("closure variables")
            continue
        a, b = left[0], right[0]
        if a.opname != b.opname:
            raise differs(f"instruction {a.opname}")
        if _is_variable_op(a):
            names_a, names_b = _names_of(a), _names_of(b)
            if len(names_a) != len(names_b) or not all(
                pair.name_ok(x, y, in_target=in_target, free=free) for x, y in zip(names_a, names_b, strict=True)
            ):
                raise differs(f"variable {a.opname}")
        elif a.argval != b.argval and not isinstance(a.argval, types.CodeType):
            raise differs(f"operand of {a.opname}")


def rename_parameter_bindings(source: str, ordinal: int, renames: Mapping[str, str], *, original: str) -> str:
    """Rename the body bindings of renamed parameters in rope's *source*; refuse unless provably equivalent.

    *source* is rope's output, whose definition already spells the final
    parameter names. *ordinal* locates the function (see :func:`function_ordinal`)
    and *renames* maps each original name to its final name; *original* is the
    module text before rope ran. Returns the source
    with every reference to those parameters renamed.

    Raises:
        ToolInputError: the rename cannot be proven equivalent (nothing is partially renamed).
    """
    if not renames:
        return source
    for new in renames.values():
        validate_identifier(new, "operations")
    if set(renames) & set(renames.values()):
        raise _refuse("a new name is the old name of another renamed parameter (swap or cycle)")
    tree = _parse(source)
    functions = _function_nodes(tree)
    if not 0 <= ordinal < len(functions):
        raise _refuse("the function was not found in rope's output")
    func = functions[ordinal]

    arg_edits: list[tuple[ast.Name | ast.arg, str]] = []
    for old, new in renames.items():
        matches = [a for a in _param_nodes(func.args) if a.arg == new]
        if len(matches) != 1:
            raise _refuse(f"parameter {new!r} was not found in the rewritten definition")
        arg_edits.append((matches[0], old))
    probe = _splice(source, arg_edits)
    probe_tree = _parse(probe)
    probe_func = _function_nodes(probe_tree)[ordinal]
    names = [a.arg for a in _param_nodes(probe_func.args)]
    if len(names) != len(set(names)):
        raise _refuse("an added parameter reuses the old name of a renamed parameter")

    new_names = frozenset(renames.values())
    stringified = _has_future_annotations(probe_tree)
    targets: list[tuple[ast.Name | ast.arg, str]] = []
    for old, new in renames.items():
        kinds = _own_binding_kinds(probe_func.body, old)
        if kinds - {"name"}:
            raise _refuse(f"{old!r} is rebound by a {'/'.join(sorted(kinds - {'name'}))} statement in the function")
        collector = ParameterCollector(old, new_names, stringified_annotations=stringified)
        collector.visit_all(probe_func.body, True)
        targets.extend((node, new) for node in collector.targets)
    probe_params = {a.arg: a for a in _param_nodes(probe_func.args)}
    targets.extend((probe_params[old], new) for old, new in renames.items())

    result = _splice(probe, targets)
    first_line = min([probe_func.lineno, *(d.lineno for d in probe_func.decorator_list)])
    _compare_code(_compile(probe), _compile(result), NamePairing(renames), (probe_func.name, first_line), "")

    # Only identifier spans may differ between the probe and the result.
    expected = ast.parse(probe)
    by_position = {(node.lineno, node.col_offset): text for node, text in targets}
    for node in ast.walk(expected):
        if isinstance(node, ast.Name | ast.arg) and (node.lineno, node.col_offset) in by_position:
            if isinstance(node, ast.Name):
                node.id = by_position[(node.lineno, node.col_offset)]
            else:
                node.arg = by_position[(node.lineno, node.col_offset)]
    if ast.dump(expected) != ast.dump(_parse(result)):
        raise _refuse("the rewrite changed more than the parameter identifiers")
    return result
