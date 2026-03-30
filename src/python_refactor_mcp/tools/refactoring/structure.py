"""Structural refactoring tools: move, module-to-package, field operations, etc."""

from __future__ import annotations

from python_refactor_mcp.models import RefactorResult

from .helpers import (
    PyrightRefactoringBackend,
    RopeRefactoringBackend,
    post_apply_diagnostics,
)


async def move_symbol(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    source_file: str,
    symbol_name: str,
    destination_file: str,
    apply: bool = False,
) -> RefactorResult:
    """Move a symbol from one file to another."""
    result = await rope.move(source_file, symbol_name, destination_file, apply)
    return await post_apply_diagnostics(pyright, result)


async def encapsulate_field(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Encapsulate a field into property accessors and optionally apply changes."""
    result = await rope.encapsulate_field(file_path, line, character, apply)
    return await post_apply_diagnostics(pyright, result)


async def use_function(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Replace similar code fragments with calls to the selected function."""
    result = await rope.use_function(file_path, line, character, apply)
    return await post_apply_diagnostics(pyright, result)


async def introduce_factory(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    factory_name: str | None = None,
    global_factory: bool = True,
    apply: bool = False,
) -> RefactorResult:
    """Introduce factory-based construction for the selected class."""
    result = await rope.introduce_factory(
        file_path,
        line,
        character,
        factory_name,
        global_factory,
        apply,
    )
    return await post_apply_diagnostics(pyright, result)


async def module_to_package(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    apply: bool = False,
) -> RefactorResult:
    """Convert a module file into a package and update references."""
    result = await rope.module_to_package(file_path, apply)
    return await post_apply_diagnostics(pyright, result)


async def local_to_field(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    apply: bool = False,
) -> RefactorResult:
    """Promote local variable usage to class field state."""
    result = await rope.local_to_field(file_path, line, character, apply)
    return await post_apply_diagnostics(pyright, result)


async def method_object(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    classname: str | None = None,
    apply: bool = False,
) -> RefactorResult:
    """Extract selected method into a new callable object class."""
    result = await rope.method_object(file_path, line, character, classname, apply)
    return await post_apply_diagnostics(pyright, result)


async def move_method(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    destination_attr: str,
    apply: bool = False,
) -> RefactorResult:
    """Move a method from one class to another via a destination attribute name."""
    result = await rope.move_method(file_path, line, character, destination_attr, apply)
    return await post_apply_diagnostics(pyright, result)


async def move_module(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    source_path: str,
    destination_package: str,
    apply: bool = False,
) -> RefactorResult:
    """Move or rename an entire module/package, updating all imports project-wide."""
    result = await rope.move_module(source_path, destination_package, apply)
    return await post_apply_diagnostics(pyright, result)


async def generate_code(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    file_path: str,
    line: int,
    character: int,
    kind: str,
    apply: bool = False,
) -> RefactorResult:
    """Generate a missing class, function, variable, module, or package from a usage site."""
    result = await rope.generate_code(file_path, line, character, kind, apply)
    return await post_apply_diagnostics(pyright, result)


async def fix_module_names(
    pyright: PyrightRefactoringBackend,
    rope: RopeRefactoringBackend,
    apply: bool = False,
) -> RefactorResult:
    """Batch-rename modules to conform to PEP 8 lowercase naming."""
    result = await rope.fix_module_names(apply)
    return await post_apply_diagnostics(pyright, result)
