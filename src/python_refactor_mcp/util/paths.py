"""Path and URI conversion helpers.

This module is the canonical location for all path ↔ URI conversions.
The ``normalize_path`` helper applies Windows drive-letter uppercasing
so that paths from different sources compare consistently.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


def normalize_path(file_path: str) -> str:
    """Return a normalized absolute path with stable Windows drive casing."""
    absolute = os.path.abspath(file_path)
    if os.name == "nt" and len(absolute) >= 2 and absolute[1] == ":":
        absolute = absolute[0].upper() + absolute[1:]
    return absolute


def path_to_uri(path: str) -> str:
    """Convert an OS-native path into a file URI."""
    return Path(normalize_path(path)).as_uri()


def uri_to_path(uri: str) -> str:
    """Convert a file URI to an OS-native absolute path."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Unsupported URI scheme: {parsed.scheme}")

    decoded_path = unquote(parsed.path)
    if os.name == "nt":
        if decoded_path.startswith("/") and len(decoded_path) >= 3 and decoded_path[2] == ":":
            decoded_path = decoded_path[1:]
        decoded_path = decoded_path.replace("/", "\\")
    return normalize_path(decoded_path)
