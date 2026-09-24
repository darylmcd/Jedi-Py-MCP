"""Custom exception types for the MCP server."""

from typing import ClassVar


class BackendError(Exception):
    """Base error for backend failures with a caller-safe public summary.

    The exception message is internal diagnostic context and may contain paths,
    provider output, or other request-adjacent data. MCP boundaries must expose
    ``caller_summary`` instead of serializing ``str(exc)``.
    """

    code: ClassVar[str] = "BACKEND"
    caller_summary: ClassVar[str] = (
        "Backend operation failed; retry the request or inspect server diagnostics."
    )


class ToolInputError(ValueError):
    """Raised when a tool call is rejected because of the caller's own input.

    Unlike ``BackendError``, the message IS the caller-facing contract: the MCP
    boundary surfaces it verbatim as ``[INVALID_INPUT] <message>``. Messages must
    name the offending parameter and the reason, and may only echo values the
    caller supplied or user-facing choices (e.g. available code-action titles) —
    never raw provider output, tracebacks, or server-internal state.

    Subclasses ``ValueError`` so existing ``except ValueError`` handlers keep
    working; it deliberately does not subclass ``BackendError`` so the backend
    redaction contract is unchanged.
    """

    code: ClassVar[str] = "INVALID_INPUT"


class PyrightError(BackendError):
    """Raised when Pyright backend operations fail."""

    code = "PYRIGHT_BACKEND"
    caller_summary = "Type-analysis backend failed; check server_status and retry."


class LspFeatureUnsupportedError(PyrightError):
    """Raised when the running Pyright does not implement a requested LSP feature.

    Covers both an advertised-capability miss recorded at ``initialize`` and a
    ``-32601 Unhandled method`` reply, so the caller sees an explicit
    unsupported error instead of a silent empty result.
    """

    code = "LSP_UNSUPPORTED"
    caller_summary = (
        "The running Pyright language server does not implement this LSP feature, "
        "so no data is available; do not retry with the same server version."
    )


class JediError(BackendError):
    """Raised when Jedi backend operations fail."""

    code = "JEDI_BACKEND"
    caller_summary = "Fallback analysis backend failed; check server_status and retry."


class RopeError(BackendError):
    """Raised when rope backend operations fail."""

    code = "ROPE_BACKEND"
    caller_summary = "Refactoring backend failed; inspect server diagnostics before retrying."


class ConfigError(BackendError):
    """Raised when server configuration discovery fails."""

    code = "CONFIG"
    caller_summary = "Server configuration is invalid; inspect server diagnostics."


class WorkspaceResolutionError(BackendError):
    """Raised when a file path cannot be mapped to any known workspace root."""

    code = "WORKSPACE_RESOLUTION"
    caller_summary = "Workspace resolution failed; provide a path within a configured workspace."
