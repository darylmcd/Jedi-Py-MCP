"""Regression coverage for ``manifest.json`` conformance to the MCPB v0.3 manifest schema.

The schema at ``tests/unit/data/mcpb-manifest-v0.3.schema.json`` is vendored byte-for-byte from
https://github.com/modelcontextprotocol/mcpb/blob/70fe3b34cd6dff1b3bba046638edc72a6467a4fb/schemas/mcpb-manifest-v0.3.schema.json
(fetched 2026-09-24). Re-fetch it when ``manifest_version`` moves past ``0.3``.
"""

from __future__ import annotations

import json
import re
import shutil
import tomllib
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

from scripts.bump_reinstall import ReleaseFiles, ReleaseVersion, read_release_version, update_version_surfaces

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "manifest.json"
SCHEMA_PATH = Path(__file__).resolve().parent / "data" / "mcpb-manifest-v0.3.schema.json"
_USER_CONFIG_REF = re.compile(r"\$\{user_config\.([A-Za-z0-9_]+)\}")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_errors(manifest: Any) -> list[str]:
    validator = Draft7Validator(_load_json(SCHEMA_PATH))
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(manifest)
    ]


def _string_values(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [value for child in node.values() for value in _string_values(child)]
    if isinstance(node, list):
        return [value for child in node for value in _string_values(child)]
    return []


def test_vendored_schema_is_the_v0_3_draft7_schema() -> None:
    schema = _load_json(SCHEMA_PATH)

    Draft7Validator.check_schema(schema)
    assert schema["properties"]["manifest_version"]["const"] == "0.3"


def test_manifest_conforms_to_mcpb_v0_3_schema() -> None:
    manifest = _load_json(MANIFEST_PATH)

    assert manifest["manifest_version"] == "0.3"
    assert _schema_errors(manifest) == []


def test_schema_rejects_the_legacy_string_author_shape() -> None:
    manifest = _load_json(MANIFEST_PATH)
    manifest["author"] = "darylmcd"

    errors = _schema_errors(manifest)

    assert errors
    assert all(error.startswith("author:") for error in errors)


def test_manifest_versions_match_pyproject() -> None:
    manifest = _load_json(MANIFEST_PATH)
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert manifest["version"] == pyproject["project"]["version"]
    assert manifest["compatibility"]["runtimes"]["python"] == pyproject["project"]["requires-python"]


def test_every_user_config_reference_resolves() -> None:
    manifest = _load_json(MANIFEST_PATH)
    declared = set(manifest.get("user_config", {}))

    referenced = {
        match.group(1)
        for value in _string_values(manifest["server"])
        for match in _USER_CONFIG_REF.finditer(value)
    }

    assert referenced
    assert referenced <= declared


def test_bump_round_trip_keeps_manifest_schema_valid(tmp_path: Path) -> None:
    package_dir = tmp_path / "src" / "python_refactor_mcp"
    package_dir.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    shutil.copyfile(REPO_ROOT / "src" / "python_refactor_mcp" / "__init__.py", package_dir / "__init__.py")
    shutil.copyfile(MANIFEST_PATH, tmp_path / "manifest.json")
    files = ReleaseFiles.from_root(tmp_path)

    current = read_release_version(files)
    target = current.bump("patch")
    update_version_surfaces(files, current, target)

    assert read_release_version(files) == target
    bumped = _load_json(files.manifest)
    assert ReleaseVersion.parse(bumped["version"]) == target
    assert _schema_errors(bumped) == []
