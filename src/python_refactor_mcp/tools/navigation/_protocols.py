"""Protocol definitions for navigation backends shared across submodules."""

from __future__ import annotations

from typing import Protocol

from python_refactor_mcp.models import (
    CallHierarchyItem,
    FoldingRange,
    Location,
    Position,
    SelectionRangeResult,
    SymbolOutlineItem,
    TypeHierarchyItem,
)


class _PyrightNavigationBackend(Protocol):
    """Protocol describing Pyright navigation methods used by this module."""

    async def prepare_call_hierarchy(
        self,
        file_path: str,
        line: int,
        char: int,
    ) -> list[CallHierarchyItem]:
        """Prepare call hierarchy item(s) for traversal."""
        ...

    async def get_incoming_calls(self, item: CallHierarchyItem) -> list[CallHierarchyItem]:
        """Return direct callers of a hierarchy item."""
        ...

    async def get_outgoing_calls(self, item: CallHierarchyItem) -> list[CallHierarchyItem]:
        """Return direct callees of a hierarchy item."""
        ...

    async def get_definition(self, file_path: str, line: int, char: int) -> list[Location]:
        """Return definition locations for a source position."""
        ...

    async def get_document_symbols(self, file_path: str) -> list[SymbolOutlineItem]:
        """Return document symbols for a file."""
        ...

    async def get_implementation(self, file_path: str, line: int, char: int) -> list[Location]:
        """Return implementation locations for a source position."""
        ...

    async def get_declaration(self, file_path: str, line: int, char: int) -> list[Location]:
        """Return declaration locations for a source position."""
        ...

    async def get_type_definition(self, file_path: str, line: int, char: int) -> list[Location]:
        """Return type definition locations for a source position."""
        ...

    async def get_folding_ranges(self, file_path: str) -> list[FoldingRange]:
        """Return foldable source ranges for a file."""
        ...

    async def prepare_type_hierarchy(self, file_path: str, line: int, char: int) -> list[TypeHierarchyItem]:
        """Prepare type hierarchy item(s) for traversal."""
        ...

    async def get_supertypes(self, item: TypeHierarchyItem) -> list[TypeHierarchyItem]:
        """Return direct supertypes of a hierarchy item."""
        ...

    async def get_subtypes(self, item: TypeHierarchyItem) -> list[TypeHierarchyItem]:
        """Return direct subtypes of a hierarchy item."""
        ...

    async def get_selection_range(self, file_path: str, positions: list[Position]) -> list[SelectionRangeResult]:
        """Return nested selection ranges for one or more positions."""
        ...


class _JediNavigationBackend(Protocol):
    """Protocol describing Jedi navigation methods used by this module."""

    async def goto_definition(self, file_path: str, line: int, character: int) -> list[Location]:
        """Return definition locations using Jedi."""
        ...
