# Jedi-Py-MCP

[![CI](https://github.com/darylmcd/Jedi-Py-MCP/actions/workflows/ci.yml/badge.svg)](https://github.com/darylmcd/Jedi-Py-MCP/actions/workflows/ci.yml)

Production-oriented Python MCP server for code analysis and refactoring, combining three backends behind bounded tool profiles.

| Backend | Role |
|---------|------|
| Pyright | Semantic analysis, references, diagnostics, definitions, call hierarchy |
| Jedi | Fallback analysis for dynamic or weakly typed code |
| rope | Edit generation and refactoring-safe file mutations |

**103-tool catalog** across analysis, navigation, refactoring, search, metrics, history, and utilities. Default `refactoring` profile advertises 70; read-only `analysis` profile advertises 56. Full table: [`docs/tool-reference.md`](docs/tool-reference.md); source map: [`ai_docs/architecture.md`](ai_docs/architecture.md).

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

- Full installation, build, and MCP client configuration: [`docs/setup.md`](docs/setup.md)

## Development

```powershell
just ci    # run full local CI gate (lint, type check, test)
just --list  # see all available recipes
```

- Development setup: [`docs/setup.md`](docs/setup.md) · Merge-gate requirements: [`CI_POLICY.md`](CI_POLICY.md)

## Privacy Policy

Runs entirely on your local machine — no telemetry, no network requests, no data transmitted externally.

- Full policy: [`PRIVACY.md`](PRIVACY.md)

## Support

- **Issues:** https://github.com/darylmcd/Jedi-Py-MCP/issues
- **Discussions:** https://github.com/darylmcd/Jedi-Py-MCP/discussions
