"""Path and URI conversion helpers."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse


def path_to_uri(path: str) -> str:
    """Convert an OS path to a file URI."""
    return Path(path).resolve().as_uri()


def uri_to_path(uri: str) -> str:
    """Convert a file URI to an OS-native absolute path."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Unsupported URI scheme: {parsed.scheme}")

    raw_path = unquote(parsed.path)
    if raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
        raw_path = raw_path[1:]
    return str(Path(raw_path))


def normalize_path(path: str) -> str:
    """Normalize a path for consistent absolute path handling."""
    return str(Path(path).resolve())
