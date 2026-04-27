# Jedi-Py-MCP

[![CI](https://github.com/darylmcd/Jedi-Py-MCP/actions/workflows/ci.yml/badge.svg)](https://github.com/darylmcd/Jedi-Py-MCP/actions/workflows/ci.yml)

Jedi-Py-MCP is a production-oriented Python MCP server for analysis and refactoring. It combines three backends behind one MCP tool surface:

- Pyright for semantic analysis, references, diagnostics, definitions, and call hierarchy.
- Jedi for fallback analysis in dynamic or weakly typed code.
- rope for edit generation and refactoring-safe file mutations.

**91 MCP tools** spanning analysis, navigation, refactoring, search, metrics, history management, and utilities.

## Documentation

| Audience | Start here |
|----------|------------|
| **Humans** | [`docs/`](docs/README.md) -- setup, usage, tool reference, troubleshooting |
| **AI agents** | [`ai_docs/README.md`](ai_docs/README.md) -- routing index for agent-facing docs |
| **Session bootstrap** | [`AGENTS.md`](AGENTS.md) -- canonical read order for AI sessions |

## Quick Start

```powershell
python -m pip install -e ".[dev]"
python -m python_refactor_mcp C:\path\to\python\project
```

See [docs/setup.md](docs/setup.md) for full installation, build, and client configuration details.

## Development

```powershell
just ci    # run full local CI gate (lint, type check, test)
just --list  # see all available recipes
```

See [docs/setup.md](docs/setup.md) for development setup and [CI_POLICY.md](CI_POLICY.md) for merge-gate requirements.

## Repository Map

- `src/python_refactor_mcp/server.py`: MCP lifecycle and tool registration
- `src/python_refactor_mcp/config.py`: workspace and runtime discovery
- `src/python_refactor_mcp/models.py`: shared structured response models
- `src/python_refactor_mcp/backends/`: Pyright, Jedi, and rope integrations
- `src/python_refactor_mcp/tools/`: tool orchestration layer
- `src/python_refactor_mcp/util/`: LSP, path, and diff helpers
- `tests/unit/`: unit test suite
- `tests/integration/`: end-to-end MCP and backend coverage
- `ai_docs/`: canonical repo workflow and policy docs

## Privacy Policy

This server runs entirely on your local machine. It does not collect telemetry, make network requests, or transmit any data externally. See [PRIVACY.md](PRIVACY.md) for the full policy.

## Support

- **Issues:** https://github.com/darylmcd/Jedi-Py-MCP/issues
- **Discussions:** https://github.com/darylmcd/Jedi-Py-MCP/discussions
