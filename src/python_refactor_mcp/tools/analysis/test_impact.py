"""Select the pytest tests impacted by a set of changed symbol anchors.

For each anchor (file, line, character) this traverses the call-hierarchy
*callers* graph and keeps the callers that live in test files, emitting
best-effort pytest node IDs. Node-ID derivation is heuristic: ``<file_path>::``
plus the caller's bare symbol name. Parametrized and nested-class tests are not
resolved to pytest's exact collected IDs (documented on
:class:`TestImpactResult`).
"""

from __future__ import annotations

from pathlib import Path

from python_refactor_mcp.backends.pyright_lsp import PyrightLSPClient
from python_refactor_mcp.models import (
    CallHierarchyItem,
    SymbolAnchor,
    TestImpactEntry,
    TestImpactResult,
)
from python_refactor_mcp.tools.navigation.hierarchy import call_hierarchy


def _is_test_path(file_path: str) -> bool:
    """Match the test-file heuristic used by get_test_coverage_map."""
    return "test" in Path(file_path).name.lower() or "tests" in file_path.lower()


def _node_id(item: CallHierarchyItem) -> str:
    """Build a best-effort pytest node ID from a caller item."""
    return f"{item.file_path}::{item.name}"


async def test_impact_select(
    pyright: PyrightLSPClient,
    symbols: list[SymbolAnchor],
    depth: int = 2,
    max_items: int = 200,
) -> TestImpactResult:
    """Return the pytest tests transitively exercising each changed symbol anchor.

    ``symbols`` is a list of anchor dicts with keys ``file_path`` (required),
    ``line``, and ``character`` (both default 0). Symbols whose callers cannot
    be resolved yield an entry with empty test lists rather than an error.
    """
    entries: list[TestImpactEntry] = []
    all_node_ids: set[str] = set()
    any_truncated = False

    for anchor in symbols:
        file_path = anchor.file_path
        line = anchor.line
        character = anchor.character

        result = await call_hierarchy(
            pyright, file_path, line, character, "callers", depth, max_items
        )

        test_callers = [caller for caller in result.callers if _is_test_path(caller.file_path)]
        node_ids = sorted({_node_id(caller) for caller in test_callers})
        affected_files = sorted({caller.file_path for caller in test_callers})
        all_node_ids.update(node_ids)
        any_truncated = any_truncated or result.truncated

        entries.append(
            TestImpactEntry(
                symbol=result.item.name,
                affected_test_files=affected_files,
                pytest_node_ids=node_ids,
                truncated=result.truncated,
            )
        )

    return TestImpactResult(
        entries=entries,
        total_affected_tests=len(all_node_ids),
        truncated=any_truncated,
    )
