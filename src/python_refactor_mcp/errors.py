"""Custom exception types for the MCP server."""


class BackendError(Exception):
    """Base error for backend failures."""


class PyrightError(BackendError):
    """Raised when Pyright backend operations fail."""


class JediError(BackendError):
    """Raised when Jedi backend operations fail."""


class RopeError(BackendError):
    """Raised when rope backend operations fail."""


class ConfigError(BackendError):
    """Raised when server configuration discovery fails."""


class WorkspaceResolutionError(BackendError):
    """Raised when a file path cannot be mapped to any known workspace root."""
