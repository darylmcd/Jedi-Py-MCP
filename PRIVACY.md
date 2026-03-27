# Privacy Policy

**Effective date:** 2026-03-27

## Overview

Python Refactor MCP (python-refactor-mcp) is a local MCP server that performs Python code analysis and refactoring entirely on your machine. It does not collect, transmit, or store any personal data or telemetry.

## Data Collection

This server collects **no data**. Specifically:

- **No telemetry** is sent to any remote service.
- **No analytics** or usage tracking is performed.
- **No personal information** is collected, stored, or shared.
- **No network requests** are made by the server itself. All operations (Pyright, Jedi, rope) run locally against files on your filesystem.

## Data Processing

The server reads and writes Python source files within the workspace directory you configure. File modifications occur only when you explicitly opt in via the `apply=True` parameter on refactoring tools. No data leaves your machine.

## Third-Party Services

This server does not integrate with any third-party services, APIs, or remote endpoints.

## Contact

If you have questions about this privacy policy, open an issue at:
https://github.com/darylmcd/Jedi-Py-MCP/issues
