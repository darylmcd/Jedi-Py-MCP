"""Completion and signature help tools."""

from __future__ import annotations

import logging

from python_refactor_mcp.models import (
    CompletionItem,
    SignatureInfo,
)
from python_refactor_mcp.tools.analysis._protocols import (
    JediAnalysisBackend as _JediAnalysisBackend,
)
from python_refactor_mcp.tools.analysis._protocols import (
    PyrightAnalysisBackend as _PyrightAnalysisBackend,
)
from python_refactor_mcp.util.shared import apply_limit

_apply_limit = apply_limit
_LOGGER = logging.getLogger(__name__)


async def get_completions(
    pyright: _PyrightAnalysisBackend,
    file_path: str,
    line: int,
    character: int,
    limit: int | None = None,
) -> list[CompletionItem]:
    """Get code completion candidates from the primary analysis backend."""
    completions = await pyright.get_completions(file_path, line, character)
    sorted_items = sorted(completions, key=lambda item: (item.label, item.kind, item.detail or ""))
    limited, _ = _apply_limit(sorted_items, limit)
    return limited


async def get_signature_help(
    pyright: _PyrightAnalysisBackend,
    file_path: str,
    line: int,
    character: int,
    jedi: _JediAnalysisBackend | None = None,
) -> SignatureInfo | None:
    """Get function signature help for a call-site position.

    When *jedi* is provided and Pyright returns None, tries Jedi as a fallback.
    """
    result = await pyright.get_signature_help(file_path, line, character)
    if result is not None or jedi is None:
        return result
    try:
        return await jedi.get_signatures(file_path, line, character)
    except Exception:
        _LOGGER.debug("jedi signature help fallback failed for %s:%d:%d", file_path, line, character, exc_info=True)
        return None


