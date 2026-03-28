"""Navigation tools orchestrating symbol lookup and call/type hierarchy queries.

This package re-exports all public tool functions from its submodules so that
existing ``from python_refactor_mcp.tools.navigation import X`` imports
continue to work unchanged.
"""

from python_refactor_mcp.tools.navigation.definitions import (
    find_implementations,
    get_declaration,
    get_type_definition,
    goto_definition,
)
from python_refactor_mcp.tools.navigation.hierarchy import (
    call_hierarchy,
    type_hierarchy,
)
from python_refactor_mcp.tools.navigation.outline import (
    get_folding_ranges,
    get_symbol_outline,
    selection_range,
)

__all__ = [
    "call_hierarchy",
    "find_implementations",
    "get_declaration",
    "get_folding_ranges",
    "get_symbol_outline",
    "get_type_definition",
    "goto_definition",
    "selection_range",
    "type_hierarchy",
]
