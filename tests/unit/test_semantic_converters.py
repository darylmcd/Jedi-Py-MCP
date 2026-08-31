"""Focused tests for the semantic LibCST converters."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock

import libcst as cst
import pytest

from python_refactor_mcp.errors import BackendError
from python_refactor_mcp.models import TextEdit, TypeInfo
from python_refactor_mcp.tools import refactoring
from python_refactor_mcp.tools.refactoring import (
    dataclass_conversion,
    pydantic_conversion,
    typed_dict_conversion,
)
from python_refactor_mcp.tools.refactoring._converter_preflight import (
    contains_comment,
    is_mutable_default,
    top_level_class,
)
from python_refactor_mcp.util import cst_imports
from python_refactor_mcp.util.cst_apply import CstSourceSnapshot
from python_refactor_mcp.util.cst_apply import (
    apply_cst_transformer as apply_cst_transformer_direct,
)

# ── convert_to_dataclass (conservative LibCST conversion) ──


@pytest.mark.parametrize(
    (
        "source",
        "after_import_block",
        "expected_index",
        "preferred",
        "fallback",
        "expected_binding",
    ),
    [
        (
            '"""Module docs."""\nfrom __future__ import annotations\nimport typing as t\nclass User: pass\n',
            False,
            2,
            "TypedDict",
            "_mcp_TypedDict",
            "TypedDict",
        ),
        (
            "if enabled:\n    dataclass = object()\n_mcp_dataclass = object()\n",
            False,
            0,
            "dataclass",
            "_mcp_dataclass",
            "_mcp_dataclass_2",
        ),
        (
            "from pydantic import BaseModel as model_base\nmodel_base = object()\n",
            True,
            1,
            "model_base",
            "_mcp_model_base",
            "_mcp_model_base",
        ),
    ],
)
def test_cst_import_planning_handles_imports_collisions_and_rebindings(
    source: str,
    after_import_block: bool,
    expected_index: int,
    preferred: str,
    fallback: str,
    expected_binding: str,
) -> None:
    module = cst.parse_module(source)
    bindings = cst_imports.top_level_bindings(module)

    assert (
        cst_imports.import_insertion_index(
            module.body,
            after_import_block=after_import_block,
        )
        == expected_index
    )
    assert cst_imports.reserve_unique_binding(bindings, preferred, fallback) == expected_binding


def test_converter_preflight_selects_exactly_one_top_level_class() -> None:
    module = cst.parse_module("class Container:\n    class User: pass\n\nclass User: pass\n")

    assert top_level_class(module, "User") is module.body[1]

    with pytest.raises(BackendError, match="Top-level class 'Missing' not found"):
        top_level_class(module, "Missing")
    with pytest.raises(BackendError, match="Multiple top-level classes named 'User' found"):
        top_level_class(cst.parse_module("class User: pass\nclass User: pass\n"), "User")


def test_converter_preflight_detects_comments_without_confusing_string_content() -> None:
    assert contains_comment(cst.parse_statement("value = 1  # retained\n")) is True
    assert contains_comment(cst.parse_statement('value = "# not a comment"\n')) is False


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("{}", True),
        ("{key: value for key, value in items}", True),
        ("dict()", True),
        ("[]", True),
        ("[item for item in items]", True),
        ("list()", True),
        ("bytearray()", True),
        ("set()", True),
        ("{item for item in items}", True),
        ("()", False),
        ("tuple()", False),
        ("frozenset()", False),
        ("None", False),
    ],
)
def test_converter_preflight_classifies_only_mutable_container_literals(
    expression: str,
    expected: bool,
) -> None:
    assert is_mutable_default(cst.parse_expression(expression)) is expected


@pytest.mark.asyncio
async def test_convert_to_dataclass_does_not_reuse_late_import(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    source = (
        '"""Models."""\n'
        "from __future__ import annotations\n"
        "\n"
        "dataclass = object()\n"
        "_mcp_dataclass = object()\n"
        "\n"
        "class User:\n"
        "    def __init__(self, name: str):\n"
        "        self.name = name\n"
        "\n"
        "from dataclasses import dataclass as late_dataclass\n"
    )
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    result = await refactoring.convert_to_dataclass(pyright, str(target), "User")

    converted = result.edits[0].new_text
    generated_import = "from dataclasses import dataclass as _mcp_dataclass_2"
    assert converted.index('"""Models."""') < converted.index("from __future__ import annotations")
    assert converted.index("from __future__ import annotations") < converted.index(generated_import)
    assert converted.index(generated_import) < converted.index("class User:")
    assert "@_mcp_dataclass_2\nclass User:" in converted
    assert "from dataclasses import dataclass as late_dataclass" in converted
    compile(converted, str(target), "exec")


@pytest.mark.asyncio
async def test_convert_to_dataclass_typed_preview_preserves_source(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    source = (
        "class User:\n"
        "    def __init__(self, name: str, enabled: bool = True):\n"
        "        self.name = name\n"
        "        self.enabled = enabled\n"
        "\n"
        "    def label(self) -> str:\n"
        "        return self.name\n"
    )
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    result = await refactoring.convert_to_dataclass(pyright, str(target), "User")

    assert result.applied is False
    assert target.read_text(encoding="utf-8") == source
    assert len(result.edits) == 1
    converted = result.edits[0].new_text
    assert "from dataclasses import dataclass" in converted
    assert "@dataclass\nclass User:" in converted
    assert "    name: str\n" in converted
    assert "    enabled: bool = True\n" in converted
    assert "def __init__" not in converted
    assert "    def label(self) -> str:" in converted
    pyright.get_hover.assert_not_awaited()
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_convert_to_dataclass_uses_pyright_for_untyped_field(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    target.write_text(
        "class User:\n    def __init__(self, name):\n        self.name = name\n",
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_hover.return_value = TypeInfo(
        expression=f"{target}:1:23",
        type_string="(parameter) name: builtins.str",
        source="pyright",
    )

    result = await refactoring.convert_to_dataclass(pyright, str(target), "User")

    assert "    name: str\n" in result.edits[0].new_text
    pyright.get_hover.assert_awaited_once_with(str(target), 1, 23)


@pytest.mark.asyncio
async def test_convert_to_dataclass_apply_writes_and_refreshes(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    target.write_text(
        "class User:\n    def __init__(self, name: str):\n        self.name = name\n",
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await refactoring.convert_to_dataclass(pyright, str(target), "User", apply=True)

    assert result.applied is True
    assert "@dataclass" in target.read_text(encoding="utf-8")
    pyright.notify_file_changed.assert_awaited_once_with(str(target))
    pyright.get_diagnostics.assert_awaited_once_with(str(target))


@pytest.mark.asyncio
async def test_convert_to_dataclass_ignores_same_named_nested_class(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    target.write_text(
        "class Container:\n"
        "    class User:\n"
        "        def __init__(self, nested: str):\n"
        "            self.nested = nested\n"
        "\n"
        "class User:\n"
        "    def __init__(self, name: str):\n"
        "        self.name = name\n",
        encoding="utf-8",
    )
    pyright = AsyncMock()

    result = await refactoring.convert_to_dataclass(pyright, str(target), "User")

    converted = result.edits[0].new_text
    assert converted.count("@dataclass") == 1
    assert converted.count("def __init__") == 1
    assert "            self.nested = nested" in converted


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,error",
    [
        (
            "class User:\n    def __init__(self, name: str):\n        self.name = name.strip()\n",
            "only supports ordered direct",
        ),
        (
            "class User:\n    def __init__(self, names: list[str] = []):\n        self.names = names\n",
            "Mutable default",
        ),
    ],
)
async def test_convert_to_dataclass_rejects_unsafe_constructor_shapes(
    tmp_path: Path,
    source: str,
    error: str,
) -> None:
    target = tmp_path / "models.py"
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    with pytest.raises(BackendError, match=error):
        await refactoring.convert_to_dataclass(pyright, str(target), "User")

    assert target.read_text(encoding="utf-8") == source
    pyright.get_hover.assert_not_awaited()


@pytest.mark.parametrize(
    ("converter_name", "source", "error"),
    [
        (
            "dataclass",
            "class User:\n    def __init__(self, name: str):\n        self.name = name  # preserve this explanation\n",
            "convert_to_dataclass refuses constructors containing comments",
        ),
        (
            "pydantic",
            "class User:\n"
            "    def __init__(self, *, name: str) -> None:\n"
            "        if not name:  # preserve this explanation\n"
            '            raise ValueError("name")\n'
            "        self.name = name\n",
            "convert_to_pydantic refuses constructors containing comments",
        ),
    ],
)
@pytest.mark.asyncio
async def test_class_converters_preserve_specific_comment_rejections(
    tmp_path: Path,
    converter_name: str,
    source: str,
    error: str,
) -> None:
    target = tmp_path / "models.py"
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    with pytest.raises(BackendError, match=error):
        if converter_name == "dataclass":
            await refactoring.convert_to_dataclass(pyright, str(target), "User")
        else:
            await refactoring.convert_to_pydantic(pyright, str(target), "User")

    assert target.read_text(encoding="utf-8") == source


# ── convert_to_pydantic (bounded Pydantic v2 conversion) ──


@pytest.mark.asyncio
async def test_convert_to_pydantic_preview_preserves_validation_and_call_shape(
    tmp_path: Path,
) -> None:
    target = tmp_path / "models.py"
    source = (
        "class User:\n"
        "    def __init__(self, *, name: str, enabled: bool = True) -> None:\n"
        "        if not name.strip():\n"
        '            raise ValueError("name is required")\n'
        "        self.name = name\n"
        "        self.enabled = enabled\n"
        "\n"
        "    def label(self) -> str:\n"
        "        return self.name\n"
    )
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    result = await refactoring.convert_to_pydantic(pyright, str(target), "User")

    assert result.applied is False
    assert target.read_text(encoding="utf-8") == source
    assert len(result.edits) == 1
    converted = result.edits[0].new_text
    assert "from pydantic import BaseModel, ConfigDict, field_validator" in converted
    assert "class User(BaseModel):" in converted
    assert 'model_config = ConfigDict(extra="forbid")' in converted
    assert "    name: str\n" in converted
    assert "    enabled: bool = True\n" in converted
    assert "@field_validator('name')" in converted
    assert "if not value.strip():" in converted
    assert "def __init__" not in converted
    assert "    def label(self) -> str:" in converted
    pyright.notify_file_changed.assert_not_awaited()

    namespace: dict[str, object] = {}
    exec(compile(converted, str(target), "exec"), namespace)  # noqa: S102
    user_type = namespace["User"]
    valid = user_type(name="Ada")  # type: ignore[operator]
    assert valid.label() == "Ada"
    with pytest.raises(ValueError, match="name is required"):
        user_type(name=" ")  # type: ignore[operator]
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        user_type(name="Ada", unexpected=True)  # type: ignore[operator]
    with pytest.raises(TypeError):
        user_type("Ada")  # type: ignore[operator]


@pytest.mark.asyncio
async def test_convert_to_pydantic_apply_writes_and_refreshes(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    target.write_text(
        "class User:\n"
        "    def __init__(self, *, name: str) -> None:\n"
        "        if not name:\n"
        '            raise ValueError("name is required")\n'
        "        self.name = name\n",
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_diagnostics.return_value = []

    result = await refactoring.convert_to_pydantic(
        pyright,
        str(target),
        "User",
        apply=True,
    )

    assert result.applied is True
    assert "class User(BaseModel):" in target.read_text(encoding="utf-8")
    pyright.notify_file_changed.assert_awaited_once_with(str(target))
    pyright.get_diagnostics.assert_awaited_once_with(str(target))


@pytest.mark.asyncio
async def test_convert_to_pydantic_does_not_reuse_late_imports(tmp_path: Path) -> None:
    target = tmp_path / "models.py"
    source = (
        "class User:\n"
        "    def __init__(self, *, name: str) -> None:\n"
        "        if not name:\n"
        '            raise ValueError("name is required")\n'
        "        self.name = name\n"
        "\n"
        "from pydantic import BaseModel, ConfigDict, field_validator\n"
    )
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    result = await refactoring.convert_to_pydantic(pyright, str(target), "User")

    converted = result.edits[0].new_text
    generated_import = (
        "from pydantic import BaseModel as _mcp_pydantic_basemodel, "
        "ConfigDict as _mcp_pydantic_configdict, "
        "field_validator as _mcp_pydantic_field_validator"
    )
    assert generated_import in converted
    assert converted.index(generated_import) < converted.index("class User(")
    assert "class User(_mcp_pydantic_basemodel):" in converted

    namespace: dict[str, object] = {}
    exec(compile(converted, str(target), "exec"), namespace)  # noqa: S102
    user_type = namespace["User"]
    assert user_type(name="Ada").name == "Ada"  # type: ignore[operator]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,error",
    [
        (
            "from pydantic import *\n"
            "class User:\n"
            "    def __init__(self, *, name: str) -> None:\n"
            "        if not name:\n"
            '            raise ValueError("name")\n'
            "        self.name = name\n",
            "wildcard Pydantic imports",
        ),
        (
            "class User:\n"
            "    def __init__(self, name: str) -> None:\n"
            "        if not name:\n"
            '            raise ValueError("name")\n'
            "        self.name = name\n",
            "keyword-only parameters",
        ),
        (
            "class User:\n"
            "    def __init__(self, *, names: list[str] = list()) -> None:\n"
            "        if not names:\n"
            '            raise ValueError("names")\n'
            "        self.names = names\n",
            "Mutable default",
        ),
        (
            "class User(Base):\n"
            "    def __init__(self, *, name: str) -> None:\n"
            "        if not name:\n"
            '            raise ValueError("name")\n'
            "        self.name = name\n",
            "without bases",
        ),
        (
            "class User:\n"
            "    def __init__(self, *, name: str) -> None:\n"
            "        if not name:\n"
            '            raise ValueError("name")\n'
            "        self.name = name\n"
            "\n"
            "    @property\n"
            "    def display_name(self) -> str:\n"
            "        return self.name\n",
            "descriptors and class data are unsupported",
        ),
        (
            "class User:\n"
            "    def __init__(self, *, first: str, last: str) -> None:\n"
            "        if not first or not last:\n"
            '            raise ValueError("name")\n'
            "        self.first = first\n"
            "        self.last = last\n",
            "exactly one field",
        ),
        (
            "class User:\n"
            "    def __init__(self, *, name: str) -> None:\n"
            "        if not name:\n"
            '            raise TypeError("name")\n'
            "        self.name = name\n",
            "raise ValueError",
        ),
        (
            "class Sample:\n"
            "    def __init__(self, *, len: int) -> None:\n"
            "        if not len:\n"
            '            raise ValueError("len")\n'
            "        self.len = len\n",
            "reserved validation name",
        ),
    ],
)
async def test_convert_to_pydantic_rejects_semantic_risk_without_writing(
    tmp_path: Path,
    source: str,
    error: str,
) -> None:
    target = tmp_path / "models.py"
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    with pytest.raises(BackendError, match=error):
        class_name = "Sample" if source.startswith("class Sample:") else "User"
        await refactoring.convert_to_pydantic(pyright, str(target), class_name)

    assert target.read_text(encoding="utf-8") == source
    pyright.notify_file_changed.assert_not_awaited()


# ── convert_to_typeddict (consistent dict-literal returns) ──


def _type_info(type_string: str) -> TypeInfo:
    return TypeInfo(expression="value", type_string=type_string, source="pyright")


@pytest.mark.asyncio
async def test_convert_to_typeddict_preview_preserves_source(tmp_path: Path) -> None:
    target = tmp_path / "payloads.py"
    source = (
        'def make_user(name: str, enabled: bool) -> dict[str, object]:\n    return {"name": name, "enabled": enabled}\n'
    )
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_hover.side_effect = [_type_info("str"), _type_info("bool")]

    result = await refactoring.convert_to_typeddict(
        pyright,
        str(target),
        "make_user",
        "UserPayload",
    )

    assert result.applied is False
    assert target.read_text(encoding="utf-8") == source
    assert len(result.edits) == 1
    converted = result.edits[0].new_text
    assert "from typing import TypedDict" in converted
    assert "class UserPayload(TypedDict):\n    name: str\n    enabled: bool\n" in converted
    assert "def make_user(name: str, enabled: bool) -> UserPayload:" in converted
    compile(converted, str(target), "exec")
    assert pyright.get_hover.await_count == 2
    pyright.notify_file_changed.assert_not_awaited()


@pytest.mark.asyncio
async def test_convert_to_typeddict_accepts_consistent_branch_types(tmp_path: Path) -> None:
    target = tmp_path / "payloads.py"
    target.write_text(
        "def make_user(enabled: bool):\n"
        "    if enabled:\n"
        '        return {"name": "ready", "enabled": enabled}\n'
        '    return {"name": "waiting", "enabled": enabled}\n',
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_hover.side_effect = [
        _type_info("Literal['ready']"),
        _type_info("bool"),
        _type_info("Literal['waiting']"),
        _type_info("bool"),
    ]

    result = await refactoring.convert_to_typeddict(
        pyright,
        str(target),
        "make_user",
        "UserPayload",
    )

    converted = result.edits[0].new_text
    assert "name: str" in converted
    assert "enabled: bool" in converted
    compile(converted, str(target), "exec")
    assert pyright.get_hover.await_count == 4


@pytest.mark.asyncio
async def test_convert_to_typeddict_apply_writes_and_refreshes(tmp_path: Path) -> None:
    target = tmp_path / "payloads.py"
    target.write_text(
        'import typing as t\n\ndef make_user(name: str):\n    return {"name": name}\n',
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_hover.return_value = _type_info("(variable) name: builtins.str")
    pyright.get_diagnostics.return_value = []

    result = await refactoring.convert_to_typeddict(
        pyright,
        str(target),
        "make_user",
        "UserPayload",
        apply=True,
    )

    assert result.applied is True
    converted = target.read_text(encoding="utf-8")
    assert "class UserPayload(t.TypedDict):" in converted
    assert "from typing import TypedDict" not in converted
    pyright.notify_file_changed.assert_awaited_once_with(str(target))
    pyright.get_diagnostics.assert_awaited_once_with(str(target))


@pytest.mark.asyncio
async def test_convert_to_typeddict_does_not_reuse_late_import(tmp_path: Path) -> None:
    target = tmp_path / "payloads.py"
    target.write_text(
        'def payload(name: str):\n    return {"name": name}\n\nfrom typing import TypedDict as LateTypedDict\n',
        encoding="utf-8",
    )
    pyright = AsyncMock()
    pyright.get_hover.return_value = _type_info("str")

    result = await refactoring.convert_to_typeddict(
        pyright,
        str(target),
        "payload",
        "Payload",
    )

    converted = result.edits[0].new_text
    assert converted.startswith("from typing import TypedDict\n\nclass Payload(TypedDict):")
    assert "from typing import TypedDict as LateTypedDict" in converted
    compile(converted, str(target), "exec")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,error",
    [
        (
            'def payload(name: str):\n    return {"name": name}\n\nclass Payload:\n    pass\n',
            "already exists",
        ),
        (
            "def payload(key: str, value: str):\n    return {key: value}\n",
            "valid identifiers",
        ),
        (
            "def payload(flag: bool):\n"
            "    if flag:\n"
            '        return {"name": "ready"}\n'
            '    return {"name": "waiting", "enabled": flag}\n',
            "same ordered keys",
        ),
        (
            'def payload(name: str) -> str:\n    return {"name": name}\n',
            "dict/mapping return annotations",
        ),
    ],
)
async def test_convert_to_typeddict_rejects_unsafe_shapes(
    tmp_path: Path,
    source: str,
    error: str,
) -> None:
    target = tmp_path / "payloads.py"
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()

    with pytest.raises(BackendError, match=error):
        await refactoring.convert_to_typeddict(
            pyright,
            str(target),
            "payload",
            "Payload",
        )

    assert target.read_text(encoding="utf-8") == source
    pyright.get_hover.assert_not_awaited()


@pytest.mark.asyncio
async def test_convert_to_typeddict_rejects_inconsistent_inferred_types(tmp_path: Path) -> None:
    target = tmp_path / "payloads.py"
    source = 'def payload(flag: bool):\n    if flag:\n        return {"value": 1}\n    return {"value": "one"}\n'
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_hover.side_effect = [_type_info("int"), _type_info("str")]

    with pytest.raises(BackendError, match="inconsistent inferred types"):
        await refactoring.convert_to_typeddict(
            pyright,
            str(target),
            "payload",
            "Payload",
        )

    assert target.read_text(encoding="utf-8") == source


@pytest.mark.asyncio
async def test_convert_to_typeddict_rejects_unknown_inferred_type(tmp_path: Path) -> None:
    target = tmp_path / "payloads.py"
    source = 'def payload(value):\n    return {"value": value}\n'
    target.write_text(source, encoding="utf-8")
    pyright = AsyncMock()
    pyright.get_hover.return_value = _type_info("Unknown")

    with pytest.raises(BackendError, match="could not infer a concrete type"):
        await refactoring.convert_to_typeddict(
            pyright,
            str(target),
            "payload",
            "Payload",
        )

    assert target.read_text(encoding="utf-8") == source


@pytest.mark.parametrize("converter_name", ["dataclass", "pydantic", "typeddict"])
@pytest.mark.asyncio
async def test_semantic_converters_reject_drift_between_planning_and_transform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    converter_name: str,
) -> None:
    target = tmp_path / "models.py"
    pyright = AsyncMock()
    pyright.get_hover.return_value = _type_info("str")
    converter_module: ModuleType

    if converter_name == "dataclass":
        source = "class User:\n    def __init__(self, name: str):\n        self.name = name\n"
        converter_module = dataclass_conversion
    elif converter_name == "pydantic":
        source = (
            "class User:\n"
            "    def __init__(self, *, name: str) -> None:\n"
            "        if not name:\n"
            "            raise ValueError('name required')\n"
            "        self.name = name\n"
        )
        converter_module = pydantic_conversion
    else:
        source = "def payload(name: str):\n    return {'name': name}\n"
        converter_module = typed_dict_conversion

    target.write_text(source, encoding="utf-8")
    newer_source = "external = True\n"

    def inject_drift(
        file_path: str,
        transformer: cst.CSTTransformer,
        *,
        apply: bool = False,
        source_snapshot: CstSourceSnapshot | None = None,
    ) -> tuple[list[TextEdit], list[str]]:
        target.write_text(newer_source, encoding="utf-8")
        return apply_cst_transformer_direct(
            file_path,
            transformer,
            apply=apply,
            source_snapshot=source_snapshot,
        )

    monkeypatch.setattr(converter_module, "apply_cst_transformer", inject_drift)

    with pytest.raises(BackendError, match="Stale edit source changed during CST planning"):
        if converter_name == "dataclass":
            await refactoring.convert_to_dataclass(pyright, str(target), "User")
        elif converter_name == "pydantic":
            await refactoring.convert_to_pydantic(pyright, str(target), "User")
        else:
            await refactoring.convert_to_typeddict(
                pyright,
                str(target),
                "payload",
                "Payload",
            )

    assert target.read_text(encoding="utf-8") == newer_source
