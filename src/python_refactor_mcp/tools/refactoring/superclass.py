"""Extract a new base class from a subset of an existing class's members.

Built on the in-repo LibCST foundation (:mod:`python_refactor_mcp.util.cst_apply`)
rather than rope — rope 1.14 ships no ``ExtractSuperclass`` refactoring. The
transformer hoists a named subset of plain methods and class-level attribute
assignments into a freshly-created base class inserted immediately before the
source class, and adds the new base to the source class's bases.

Only plain ``def`` methods and class-level assignments hoist. The transformer
raises :class:`BackendError` for unsupported member kinds — ``@classmethod`` /
``@staticmethod`` / ``@property`` methods, ``__slots__``, and anything not found
as a direct member of the class body (which includes ``__init__``-assigned
instance attributes, since those are not class-level statements).
"""

from __future__ import annotations

import libcst as cst

from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient
from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import RefactorResult
from python_refactor_mcp.util.cst_apply import apply_cst_transformer

from .helpers import post_apply_diagnostics

_REJECTED_DECORATORS = frozenset({"classmethod", "staticmethod", "property"})


def _decorator_base_name(decorator: cst.Decorator) -> str:
    """Return the rightmost name of a decorator expression (``@a.b.c`` -> ``c``)."""
    node: cst.BaseExpression = decorator.decorator
    if isinstance(node, cst.Call):
        node = node.func
    if isinstance(node, cst.Attribute):
        return node.attr.value
    if isinstance(node, cst.Name):
        return node.value
    return ""


def _statement_member_name(statement: cst.BaseStatement) -> str | None:
    """Return the member name a class-body statement defines, or None.

    Recognizes plain ``def`` methods and single-target class-level assignments
    (``x = ...`` / ``x: T = ...``). Everything else returns None and is left in
    the source class.
    """
    if isinstance(statement, cst.FunctionDef):
        return statement.name.value
    if isinstance(statement, cst.SimpleStatementLine):
        for small in statement.body:
            if isinstance(small, cst.Assign):
                if len(small.targets) == 1 and isinstance(small.targets[0].target, cst.Name):
                    return small.targets[0].target.value
            elif isinstance(small, cst.AnnAssign) and isinstance(small.target, cst.Name):
                return small.target.value
    return None


class ExtractSuperclassTransformer(cst.CSTTransformer):
    """Hoist named members of *source_class* into a new *base_class_name*."""

    def __init__(self, source_class: str, base_class_name: str, members: list[str]) -> None:
        super().__init__()
        self._source_class = source_class
        self._base_class_name = base_class_name
        self._requested = list(members)
        self.class_found = False

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.BaseStatement | cst.FlattenSentinel[cst.BaseStatement]:
        if original_node.name.value != self._source_class:
            return updated_node
        self.class_found = True

        block = updated_node.body
        if not isinstance(block, cst.IndentedBlock):
            # A class body is always an indented block in real source; bail safely otherwise.
            return updated_node

        requested = set(self._requested)
        found: set[str] = set()
        hoisted: list[cst.BaseStatement] = []
        remaining: list[cst.BaseStatement] = []

        for statement in block.body:
            name = _statement_member_name(statement)
            if name is None or name not in requested:
                remaining.append(statement)
                continue
            if name == "__slots__":
                raise BackendError(f"Cannot hoist {name!r}: __slots__ is not supported")
            if isinstance(statement, cst.FunctionDef):
                for decorator in statement.decorators:
                    rejected = _decorator_base_name(decorator)
                    if rejected in _REJECTED_DECORATORS:
                        raise BackendError(
                            f"Cannot hoist {name!r}: @{rejected}-decorated members are not supported"
                        )
            found.add(name)
            hoisted.append(statement)

        missing = requested - found
        if missing:
            raise BackendError(
                f"Member(s) not found as hoistable members of class {self._source_class!r}: "
                f"{sorted(missing)}"
            )

        new_base = cst.ClassDef(
            name=cst.Name(self._base_class_name),
            body=cst.IndentedBlock(body=hoisted),
        )
        remaining_body: list[cst.BaseStatement] = remaining or [
            cst.SimpleStatementLine(body=[cst.Pass()])
        ]
        new_bases = [*updated_node.bases, cst.Arg(value=cst.Name(self._base_class_name))]
        modified = updated_node.with_changes(
            body=block.with_changes(body=remaining_body),
            bases=new_bases,
        )
        return cst.FlattenSentinel([new_base, modified])


async def extract_superclass(
    pyright: PyrightLSPClient,
    file_path: str,
    class_name: str,
    base_class_name: str,
    members: list[str],
    apply: bool = False,
) -> RefactorResult:
    """Pull *members* of *class_name* up into a new *base_class_name*.

    Defaults to preview mode (``apply=False``). Raises :class:`BackendError`
    when *members* is empty, the class is absent, a member is not a hoistable
    class-level member, or a member is an unsupported kind.
    """
    if not members:
        raise BackendError("extract_superclass requires at least one member to hoist")

    transformer = ExtractSuperclassTransformer(class_name, base_class_name, members)
    edits, files_affected = apply_cst_transformer(file_path, transformer, apply=apply)

    if not transformer.class_found:
        raise BackendError(f"Class {class_name!r} not found in {file_path}")

    description = (
        f"Extracted superclass {base_class_name} from {class_name} "
        f"with {len(members)} member(s)"
    )
    result = RefactorResult(
        edits=edits,
        files_affected=files_affected,
        description=description,
        applied=bool(apply and edits),
    )
    if apply and edits:
        return await post_apply_diagnostics(pyright, result)
    return result
