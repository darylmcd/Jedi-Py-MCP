"""Type stub generation tool using Pyright's createtypestub command."""

from __future__ import annotations

from typing import Protocol


class _PyrightStubBackend(Protocol):
    """Protocol describing the Pyright method needed for stub generation."""

    async def create_type_stub(self, package_name: str, output_dir: str | None = None) -> bool: ...


async def create_type_stubs(
    pyright: _PyrightStubBackend,
    package_name: str,
    output_dir: str | None = None,
) -> bool:
    """Generate .pyi stub files for a third-party package lacking type information."""
    return await pyright.create_type_stub(package_name, output_dir)
