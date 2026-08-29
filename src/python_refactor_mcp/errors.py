"""Custom exception types for the MCP server."""

from typing import ClassVar


class BackendError(Exception):
    """Base error for backend failures."""

    code: ClassVar[str] = "BACKEND"


class PyrightError(BackendError):
    """Raised when Pyright backend operations fail."""

    code = "PYRIGHT_BACKEND"


class JediError(BackendError):
    """Raised when Jedi backend operations fail."""

    code = "JEDI_BACKEND"


class RopeError(BackendError):
    """Raised when rope backend operations fail."""

    code = "ROPE_BACKEND"


class ConfigError(BackendError):
    """Raised when server configuration discovery fails."""

    code = "CONFIG"


class WorkspaceResolutionError(BackendError):
    """Raised when a file path cannot be mapped to any known workspace root."""

    code = "WORKSPACE_RESOLUTION"
