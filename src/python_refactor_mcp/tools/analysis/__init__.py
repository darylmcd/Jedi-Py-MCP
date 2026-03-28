"""Analysis tools orchestrating Pyright and Jedi backends."""

from python_refactor_mcp.tools.analysis.completions import (
    get_call_signatures_fallback,
    get_completions,
    get_signature_help,
)
from python_refactor_mcp.tools.analysis.diagnostics import (
    get_diagnostics,
    get_workspace_diagnostics,
)
from python_refactor_mcp.tools.analysis.jedi_extras import (
    deep_type_inference,
    get_all_names,
    get_context,
    get_syntax_errors,
    get_type_hint_string,
)
from python_refactor_mcp.tools.analysis.references import find_references
from python_refactor_mcp.tools.analysis.static_errors import find_errors_static
from python_refactor_mcp.tools.analysis.type_stubs import create_type_stubs
from python_refactor_mcp.tools.analysis.tokens import (
    get_document_highlights,
    get_inlay_hints,
    get_semantic_tokens,
)
from python_refactor_mcp.tools.analysis.type_info import (
    get_documentation,
    get_hover_info,
    get_type_info,
)

__all__ = [
    "create_type_stubs",
    "deep_type_inference",
    "find_errors_static",
    "find_references",
    "get_all_names",
    "get_call_signatures_fallback",
    "get_completions",
    "get_context",
    "get_diagnostics",
    "get_document_highlights",
    "get_documentation",
    "get_hover_info",
    "get_inlay_hints",
    "get_semantic_tokens",
    "get_signature_help",
    "get_syntax_errors",
    "get_type_hint_string",
    "get_type_info",
    "get_workspace_diagnostics",
]
