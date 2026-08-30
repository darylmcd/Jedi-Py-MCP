"""Codemod that fixes SEC022 (`yaml.load` without a safe loader).

Rewrites ``yaml.load(stream)`` to ``yaml.safe_load(stream)`` via the shared
LibCST apply foundation. Conservative by design: a call that already passes an
explicit ``Loader=`` (keyword or second positional) — or uses ``*args`` we
cannot reason about — is left untouched and counted as a skip, since an
explicit loader choice may be deliberate.

Scope (slice 1): only the literal ``yaml.load`` attribute call is matched,
mirroring the SEC022 scanner in ``tools/metrics/security.py``. Alias forms
(``import yaml as y; y.load(...)``) and ``from yaml import load`` are a
documented follow-up. The match is syntactic, so a shadowed local named
``yaml`` (``yaml = something(); yaml.load(...)``) would also be rewritten —
the same blind spot the scanner has; preview-by-default and the
the destructive tool annotation are the mitigation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import libcst as cst

from python_refactor_mcp.models import RefactorResult
from python_refactor_mcp.tools.refactoring.helpers import post_apply_diagnostics
from python_refactor_mcp.util.cst_apply import apply_cst_transformer_batch

if TYPE_CHECKING:
    from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient


class _YamlLoadSafener(cst.CSTTransformer):
    """Rewrite eligible ``yaml.load(...)`` calls to ``yaml.safe_load(...)``."""

    def __init__(self) -> None:
        self.rewrites = 0
        self.skips = 0

    def leave_Call(self, original_node: cst.Call, updated_node: cst.Call) -> cst.BaseExpression:
        func = original_node.func
        if not (
            isinstance(func, cst.Attribute)
            and isinstance(func.value, cst.Name)
            and func.value.value == "yaml"
            and func.attr.value == "load"
        ):
            return updated_node

        # Conservative skip: anything we cannot fully reason about.
        if any(arg.star for arg in original_node.args):
            self.skips += 1
            return updated_node

        has_loader_kw = any(
            arg.keyword is not None and arg.keyword.value == "Loader" for arg in original_node.args
        )
        positional = [arg for arg in original_node.args if arg.keyword is None]
        if has_loader_kw or len(positional) >= 2:
            self.skips += 1
            return updated_node

        self.rewrites += 1
        assert isinstance(updated_node.func, cst.Attribute)
        return updated_node.with_changes(
            func=updated_node.func.with_changes(attr=cst.Name("safe_load")),
        )


async def security_autofix(
    pyright: PyrightLSPClient,
    file_path: str | None = None,
    file_paths: list[str] | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Rewrite unsafe ``yaml.load()`` calls (SEC022) to ``yaml.safe_load()``.

    Targets the literal ``yaml.load`` attribute call. Calls that already pass an
    explicit ``Loader=`` are skipped (counted in the description). Defaults to
    preview mode; ``apply=True`` writes edits atomically and refreshes Pyright
    diagnostics for the changed files.
    """
    targets: list[str] = list(file_paths) if file_paths else []
    if file_path is not None:
        targets.append(file_path)

    if not targets:
        return RefactorResult(
            edits=[], files_affected=[], description="No files provided to scan", applied=False
        )

    transformers: list[_YamlLoadSafener] = []

    def _factory(_file_path: str) -> cst.CSTTransformer:
        transformer = _YamlLoadSafener()
        transformers.append(transformer)
        return transformer

    edits, files_affected = apply_cst_transformer_batch(targets, _factory, apply=apply)
    rewrites = sum(transformer.rewrites for transformer in transformers)
    skips = sum(transformer.skips for transformer in transformers)

    if not edits:
        if skips:
            description = f"No rewritable yaml.load() calls; skipped {skips} with an explicit Loader="
        else:
            description = "No unsafe yaml.load() calls found"
        return RefactorResult(edits=[], files_affected=[], description=description, applied=False)

    description = (
        f"Rewrote {rewrites} yaml.load() -> yaml.safe_load() across {len(files_affected)} file(s)"
    )
    if skips:
        description += f"; skipped {skips} with an explicit Loader="
    result = RefactorResult(edits=edits, files_affected=files_affected, description=description, applied=apply)
    if apply:
        return await post_apply_diagnostics(pyright, result)
    return result
