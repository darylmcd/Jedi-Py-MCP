"""Unit tests for the parameter-rename body pass (generator plus compiled-code oracle)."""

from __future__ import annotations

import ast
import re
import runpy
from pathlib import Path
from typing import Any

import pytest

from python_refactor_mcp.errors import ToolInputError
from python_refactor_mcp.util.param_rename import (
    BINDING_FIELDS,
    NamePairing,
    ParameterCollector,
    function_ordinal,
    rename_parameter_bindings,
    require_other_definitions_untouched,
)
from python_refactor_mcp.util.shared import validate_identifier

# ``ast`` string fields that are labels or text, never variable references (exhaustiveness test below).
LABEL_FIELDS: dict[type[ast.AST], tuple[str, ...]] = {
    ast.Attribute: ("attr",),
    ast.keyword: ("arg",),
    ast.MatchClass: ("kwd_attrs",),
    ast.ImportFrom: ("module",),
    ast.Constant: ("value", "kind"),
    ast.Interpolation: ("str",),
    ast.TypeIgnore: ("tag",),
    ast.Assign: ("type_comment",),
    ast.AsyncFor: ("type_comment",),
    ast.AsyncFunctionDef: ("type_comment",),
    ast.AsyncWith: ("type_comment",),
    ast.For: ("type_comment",),
    ast.FunctionDef: ("type_comment",),
    ast.With: ("type_comment",),
    ast.arg: ("type_comment",),
}


def _as_rope_output(source: str, old: str, new: str) -> str:
    """Spell the renamed parameter in the definition header, as rope's output does."""
    lines = source.splitlines(keepends=True)
    index = next(i for i, line in enumerate(lines) if re.search(r"\bdef f\b", line))
    lines[index] = re.sub(rf"\b{old}\b", new, lines[index], count=1)
    return "".join(lines)


def _rename(source: str, old: str = "b", new: str = "n", *, ordinal: int = 0) -> str:
    return rename_parameter_bindings(_as_rope_output(source, old, new), ordinal, {old: new}, original=source)


def _fn(body: str, header: str = "def f(a, b):") -> str:
    return header + "\n" + "".join(f"    {line}\n" for line in body.split("\n"))


# (id, original source, expected result with b renamed to n, or None for a typed refusal)
CASES: list[tuple[str, str, str | None]] = [
    ("simple", _fn("return b + a"), _fn("return n + a", "def f(a, n):")),
    (
        "walrus_in_comprehension",
        _fn("r = [(b := x) for x in a]\nreturn b"),
        _fn("r = [(n := x) for x in a]\nreturn n", "def f(a, n):"),
    ),
    ("comprehension_own_binding", _fn("return [x for x in a for b in x if b]"), None),
    ("comprehension_reads_own_binding", _fn("return [b for x in a for b in b]"), None),
    ("comprehension_first_iterable", _fn("return [x for x in b for b in x]"), None),
    (
        "generator_own_variable",
        _fn("return list(b for b in a), b"),
        _fn("return list(b for b in a), n", "def f(a, n):"),
    ),
    (
        "keyword_pattern_attribute",
        _fn("match a:\n    case P(b=1):\n        return b"),
        _fn("match a:\n    case P(b=1):\n        return n", "def f(a, n):"),
    ),
    (
        "class_body_rebinds_through_globals",
        _fn("class C:\n    b = b\nreturn C, b"),
        _fn("class C:\n    b = b\nreturn C, n", "def f(a, n):"),
    ),
    (
        "class_body_free_read",
        _fn("class C:\n    y = b\nreturn C"),
        _fn("class C:\n    y = n\nreturn C", "def f(a, n):"),
    ),
    ("nonlocal_in_nested", _fn("def g():\n    nonlocal b\n    b = 1\nreturn g"), None),
    (
        "global_in_nested",
        _fn("def g():\n    global b\n    return b\nreturn g"),
        _fn("def g():\n    global b\n    return b\nreturn g", "def f(a, n):"),
    ),
    ("import_of_old_name", _fn("import b\nreturn b"), None),
    ("def_of_old_name", _fn("def b(): pass\nreturn b"), None),
    ("except_as_old_name", _fn("try:\n    pass\nexcept E as b:\n    return b"), None),
    ("except_star_as_old_name", _fn("try:\n    pass\nexcept* E as b:\n    return b"), None),
    ("match_star_capture", _fn("match a:\n    case [x, *b]:\n        return b"), None),
    ("match_class_capture", _fn("match a:\n    case P(x=b):\n        return b"), None),
    ("type_parameter_named_old", _fn("def g[b](x: b):\n    return x\nreturn g"), None),
    (
        "nested_parameter_shadows",
        _fn("def g(b):\n    return b\nreturn g(b)"),
        _fn("def g(b):\n    return b\nreturn g(n)", "def f(a, n):"),
    ),
    (
        "lambda_shadow_and_free",
        _fn("return (lambda b: b)(1), (lambda: b)"),
        _fn("return (lambda b: b)(1), (lambda: n)", "def f(a, n):"),
    ),
    (
        "decorator_and_default_of_nested",
        _fn("@deco(b)\ndef g(c=b):\n    return c\nreturn g"),
        _fn("@deco(n)\ndef g(c=n):\n    return c\nreturn g", "def f(a, n):"),
    ),
    (
        "annotation_of_nested",
        _fn("def g(c: b) -> b:\n    return c\nreturn g"),
        _fn("def g(c: n) -> n:\n    return c\nreturn g", "def f(a, n):"),
    ),
    (
        "future_annotations_are_strings",
        "from __future__ import annotations\n" + _fn("def g(c: b) -> b:\n    return c\nreturn g"),
        "from __future__ import annotations\n" + _fn("def g(c: b) -> b:\n    return c\nreturn g", "def f(a, n):"),
    ),
    (
        "string_annotation",
        _fn("def g(c: 'b'):\n    return c\nreturn g"),
        _fn("def g(c: 'b'):\n    return c\nreturn g", "def f(a, n):"),
    ),
    ("local_annotation", _fn("x: b = 1\nreturn x"), _fn("x: n = 1\nreturn x", "def f(a, n):")),
    (
        "type_statement_and_type_parameter_bound",
        _fn("type X[T] = list[b]\ndef g[T: b](x: T):\n    return x\nreturn g"),
        _fn("type X[T] = list[n]\ndef g[T: n](x: T):\n    return x\nreturn g", "def f(a, n):"),
    ),
    (
        "except_with_other_name",
        _fn("try:\n    return b\nexcept E as e:\n    return b, e"),
        _fn("try:\n    return n\nexcept E as e:\n    return n, e", "def f(a, n):"),
    ),
    ("del_statement", _fn("del b"), _fn("del n", "def f(a, n):")),
    ("star_target", _fn("x, *b = a\nreturn b"), _fn("x, *n = a\nreturn n", "def f(a, n):")),
    ("augmented_assignment", _fn("b += 1\nreturn b"), _fn("n += 1\nreturn n", "def f(a, n):")),
    (
        "with_and_for_targets",
        _fn("with a as b:\n    pass\nfor b in a:\n    pass\nreturn b"),
        _fn("with a as n:\n    pass\nfor n in a:\n    pass\nreturn n", "def f(a, n):"),
    ),
    (
        "positional_only_and_keyword_only",
        _fn("return b + c", "def f(a, /, b, *, c):"),
        _fn("return n + c", "def f(a, /, n, *, c):"),
    ),
    ("fstring", _fn("return f'{b!r:>{b}} {a}'"), _fn("return f'{n!r:>{n}} {a}'", "def f(a, n):")),
    ("fstring_debug_text", _fn("return f'{b=}'"), None),
    ("template_string", _fn("return t'{b}'"), None),
    ("new_name_used_as_local", _fn("n = 1\nreturn b + n"), None),
    ("new_name_used_as_comprehension_variable", _fn("return [n for n in a], b"), None),
    (
        "new_name_as_attribute_and_keyword",
        _fn("return a.n, g(n=1), b"),
        _fn("return a.n, g(n=1), n", "def f(a, n):"),
    ),
    ("dynamic_locals", _fn("return locals(), b"), None),
    ("dynamic_vars_nested", _fn("def g():\n    return vars()\nreturn g"), None),
    ("dynamic_eval", _fn("return eval('b')"), None),
    ("dynamic_f_locals", _fn("import sys\nreturn sys._getframe().f_locals['b']"), None),
    ("dynamic_builtins_locals", _fn("import builtins\nreturn builtins.locals()"), None),
    ("dynamic_builtins_eval", _fn("import builtins\nreturn builtins.eval('b')"), None),
    ("dynamic_getargvalues", _fn("import inspect\nreturn inspect.getargvalues(inspect.stack()[0].frame).locals"), None),
    ("dynamic_currentframe", _fn("import inspect\nreturn inspect.currentframe().f_locals"), None),
    (
        "non_ascii_text_before_name_on_the_line",
        _fn("x = 'é'; y = 'ü' + b\nreturn x, y"),
        _fn("x = 'é'; y = 'ü' + n\nreturn x, y", "def f(a, n):"),
    ),
    ("crlf_source", "def f(a, b):\r\n    x = 1\r\n    return b\r\n", "def f(a, n):\r\n    x = 1\r\n    return n\r\n"),
    ("attribute_and_keyword_names", _fn("return obj.b, g(b=b)"), _fn("return obj.b, g(b=n)", "def f(a, n):")),
    ("closure_read", _fn("def g():\n    return b\nreturn g"), _fn("def g():\n    return n\nreturn g", "def f(a, n):")),
    (
        "intermediate_scope_rebinds",
        _fn("def mid():\n    b = 1\n    def inner():\n        return b\n    return inner\nreturn mid"),
        _fn("def mid():\n    b = 1\n    def inner():\n        return b\n    return inner\nreturn mid", "def f(a, n):"),
    ),
    (
        "walrus_in_nested_comprehension",
        _fn("def g():\n    return [(b := 1) for _ in a]\nreturn g"),
        _fn("def g():\n    return [(b := 1) for _ in a]\nreturn g", "def f(a, n):"),
    ),
    ("dead_code", _fn("if False:\n    return b\nreturn 1"), _fn("if False:\n    return n\nreturn 1", "def f(a, n):")),
    (
        "default_of_the_function_is_outside_its_scope",
        _fn("return b", "def f(a, b, c=b):"),
        _fn("return n", "def f(a, n, c=b):"),
    ),
    (
        "docstring_is_not_renamed",
        _fn("'''b: the b value'''\nreturn b"),
        _fn("'''b: the b value'''\nreturn n", "def f(a, n):"),
    ),
    (
        "same_line_lambdas",
        _fn("return sorted(a, key=lambda x: x[b]) + sorted(a, key=lambda y: y)"),
        _fn("return sorted(a, key=lambda x: x[n]) + sorted(a, key=lambda y: y)", "def f(a, n):"),
    ),
    (
        "cell_sort",
        _fn("c = 1\ndef g():\n    return a, b, c\nreturn g", "def f(a, b):"),
        _fn("c = 1\ndef g():\n    return a, n, c\nreturn g", "def f(a, n):"),
    ),
    (
        "closure_two_cells",
        _fn("def g():\n    return a + b\nh = lambda: a * b\nreturn g, h", "def f(a, b):"),
        _fn("def g():\n    return a + n\nh = lambda: a * n\nreturn g, h", "def f(a, n):"),
    ),
    ("unused_parameter", _fn("return a"), _fn("return a", "def f(a, n):")),
]


@pytest.mark.parametrize(("source", "want"), [pytest.param(s, w, id=i) for i, s, w in CASES])
def test_rename_corpus(source: str, want: str | None) -> None:
    """Every case renames exactly the parameter's bindings or refuses; nothing in between."""
    if want is None:
        with pytest.raises(ToolInputError, match="parameter: operations"):
            _rename(source)
    else:
        assert _rename(source) == want


def test_private_name_mangling_is_refused() -> None:
    source = "class C:\n    def f(self, __b):\n        return __b\n"
    with pytest.raises(ToolInputError):
        _rename(source, "__b", "n")


def test_method_and_decorated_function_are_renamed() -> None:
    method = "class C:\n    def f(self, b):\n        return super().f(b)\n"
    assert _rename(method) == "class C:\n    def f(self, n):\n        return super().f(n)\n"
    decorated = "@deco\ndef f(a, b):\n    return b\n"
    assert _rename(decorated) == "@deco\ndef f(a, n):\n    return n\n"


def test_second_function_is_located_by_ordinal() -> None:
    source = "def other(a, b):\n    return b\n\n\ndef f(a, b):\n    return b\n"
    out = rename_parameter_bindings(source.replace("def f(a, b)", "def f(a, n)"), 1, {"b": "n"}, original=source)
    assert out == "def other(a, b):\n    return b\n\n\ndef f(a, n):\n    return n\n"
    assert function_ordinal(source, 5, "f") == 1


def test_two_renames_in_one_call_map_each_pair() -> None:
    source = "def f(a, b):\n    def g():\n        return a, b\n    c = 1\n    return g, a + b, c\n"
    rope_output = source.replace("def f(a, b)", "def f(y, x)")
    out = rename_parameter_bindings(rope_output, 0, {"a": "y", "b": "x"}, original=source)
    assert out == source.replace("a", "y").replace("b", "x").replace("def f(y, x)", "def f(y, x)")


def test_pairing_looks_up_each_name_never_a_single_pair() -> None:
    """``a->y`` must not pass where the renames say ``a->x`` (B2)."""
    pair = NamePairing({"a": "x", "b": "y"})
    none: frozenset[str] = frozenset()
    assert pair.name_ok("a", "x", in_target=True, free=none)
    assert pair.name_ok("b", "y", in_target=True, free=none)
    assert not pair.name_ok("a", "y", in_target=True, free=none)
    assert not pair.name_ok("b", "x", in_target=True, free=none)
    assert not pair.name_ok("a", "x", in_target=False, free=none)
    assert pair.name_ok("a", "x", in_target=False, free=frozenset({"a"}))
    assert pair.multiset_ok(["a", "b", "c"], ["c", "x", "y"], in_target=True, free=none)
    assert not pair.multiset_ok(["a", "b", "c"], ["c", "y", "y"], in_target=True, free=none)


_TWO = "def f(a, b):\n    return a, b\n"


def test_swap_and_cycle_are_refused() -> None:
    with pytest.raises(ToolInputError, match="swap or cycle"):
        rename_parameter_bindings(_TWO, 0, {"a": "b", "b": "a"}, original=_TWO)


def test_added_parameter_reusing_the_old_name_is_refused() -> None:
    with pytest.raises(ToolInputError, match="reuses the old name"):
        rename_parameter_bindings("def f(a, n, b):\n    return n, b\n", 0, {"b": "n"}, original=_TWO)


def test_unparseable_rope_output_is_refused() -> None:
    """Unparseable rope output (a synthetic ``def f(a, n, *)``) and a byte-order mark are refused.

    ``change_signature`` refuses keyword-only targets before rope runs; this guard covers any other unparseable result.
    """
    with pytest.raises(ToolInputError, match="does not parse"):
        rename_parameter_bindings("def f(a, n, *):\n    return n\n", 0, {"b": "n"}, original=_TWO)
    with pytest.raises(ToolInputError, match="does not parse"):
        rename_parameter_bindings("\ufeffdef f(a, n):\n    return n\n", 0, {"b": "n"}, original=_TWO)


def test_no_renames_returns_source_unchanged() -> None:
    assert rename_parameter_bindings("def f(a):\n    return a\n", 0, {}, original="") == "def f(a):\n    return a\n"


@pytest.mark.parametrize("name", ["class", "1x", "a-b", "", "ﬁle"])
def test_new_name_must_be_a_normalized_identifier(name: str) -> None:
    with pytest.raises(ToolInputError):
        validate_identifier(name, "new_name")


def test_oracle_refuses_a_wrong_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
    """The oracle, not the generator, is the authority: a sabotaged proposal is refused."""
    source = "def f(a, b):\n    def g(b):\n        return b\n    return g(b)\n"
    rope_output = source.replace("def f(a, b)", "def f(a, n)")
    renames = {"b": "n"}
    good = rename_parameter_bindings(rope_output, 0, renames, original=source)
    assert good.endswith("return g(n)\n")
    real_visit = ParameterCollector.visit

    def sloppy(self: ParameterCollector, node: ast.AST, active: bool) -> None:
        real_visit(self, node, True)  # ignore shadowing

    monkeypatch.setattr(ParameterCollector, "visit", sloppy)
    with pytest.raises(ToolInputError, match="differs from the original"):
        rename_parameter_bindings(rope_output, 0, renames, original=source)


def test_identifier_tables_cover_every_ast_string_field() -> None:
    """A Python release adding a string-bearing AST node must be classified, not silently skipped."""
    missing: list[str] = []
    for name in dir(ast):
        cls = getattr(ast, name)
        if not (isinstance(cls, type) and issubclass(cls, ast.AST)):
            continue
        for field, annotation in getattr(cls, "_field_types", {}).items():
            known = BINDING_FIELDS.get(cls, ()) + LABEL_FIELDS.get(cls, ())
            if "str" in repr(annotation) and field not in known:
                missing.append(f"{name}.{field}")
    assert not missing


_BEHAVIOUR = [
    ("closure", _fn("def g():\n    return a + b\nreturn g()"), (1, 2)),
    ("walrus", _fn("before = b\nr = [(b := x) for x in a]\nreturn before, b"), ([1, 2, 3], 9)),
    ("class_body", _fn("class C:\n    y = b\nreturn C.y"), (1, 5)),
    ("shadow", _fn("def g(b):\n    return b * 2\nreturn g(b) + b"), (1, 5)),
    ("loops", _fn("for b in a:\n    pass\nreturn b"), ([1, 2, 3], 0)),
    ("delete", _fn("del b\nreturn a"), (1, 2)),
    ("cells", _fn("c = 3\ndef g():\n    return a, b, c\nreturn g()"), (1, 2)),
    (
        "future_annotations",
        "from __future__ import annotations\n" + _fn("def g(c: b):\n    return c\nreturn g(b)"),
        (1, 2),
    ),
]


@pytest.mark.parametrize(("source", "args"), [pytest.param(s, a, id=i) for i, s, a in _BEHAVIOUR])
def test_renamed_function_behaves_like_the_original(tmp_path: Path, source: str, args: tuple[Any, ...]) -> None:
    before = tmp_path / "before.py"
    after = tmp_path / "after.py"
    before.write_text(source, encoding="utf-8")
    after.write_text(_rename(source), encoding="utf-8")
    assert runpy.run_path(str(before))["f"](*args) == runpy.run_path(str(after))["f"](*args)


_TWO_DEFS = "def f(a, b):\n    return a\n\n\ndef f(a, b):\n    return b\n"


def test_other_definition_with_changed_parameters_is_refused() -> None:
    rewritten = _TWO_DEFS.replace("def f(a, b):\n    return a", "def f(a):\n    return a")
    with pytest.raises(ToolInputError, match=r"another definition named 'f' \(line 1\).*\(parameter: line\)$"):
        require_other_definitions_untouched(_TWO_DEFS, rewritten, 1)


def test_other_definition_with_identical_parameters_is_accepted() -> None:
    require_other_definitions_untouched(_TWO_DEFS, _TWO_DEFS.replace("return b", "return 0"), 0)


def test_unparseable_rewritten_module_is_refused() -> None:
    """rope's keyword-only emission (``def f(a, *)``) is the real-world shape."""
    with pytest.raises(ToolInputError, match=r"produced source that does not parse.*\(parameter: line\)$"):
        require_other_definitions_untouched(_TWO_DEFS, "def f(a, *):\n    return a\n", 0)


def test_too_deeply_nested_rewritten_module_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """``ast.parse`` raises RecursionError on source nested too deeply; only the rewritten text is made to."""
    real_parse = ast.parse

    def parse(source: str, *args: Any, **kwargs: Any) -> ast.Module:
        if source == rewritten:
            raise RecursionError("maximum recursion depth exceeded during compilation")
        return real_parse(source, *args, **kwargs)

    rewritten = _TWO_DEFS.replace("return a", "return 0")
    monkeypatch.setattr(ast, "parse", parse)
    with pytest.raises(ToolInputError, match=r"produced source that does not parse.*\(parameter: line\)$"):
        require_other_definitions_untouched(_TWO_DEFS, rewritten, 0)


def test_changed_number_of_definitions_is_refused() -> None:
    with pytest.raises(ToolInputError, match=r"changed the number of function definitions.*\(parameter: line\)$"):
        require_other_definitions_untouched(_TWO_DEFS, "def f(a, b):\n    return a\n", 0)
