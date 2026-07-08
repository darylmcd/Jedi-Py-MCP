# MCP Best Practices — Testing, Deployment, SDK Patterns, Anti-Patterns, Sources
<!-- purpose: Part 4 of the MCP best-practices reference — see ./README.md for the full index. -->

## 16. Testing and Debugging

### MCP Inspector
- Official visual testing tool: `npx @modelcontextprotocol/inspector`
- Opens at `http://localhost:6274` with resource inspection, prompt testing, tool execution, real-time notification monitoring
- Shows every JSON-RPC message exchanged between client and server
- NEVER expose on a network-accessible port — bind to 127.0.0.1 only

### Multi-Layer Testing

| Type | Purpose |
|------|---------|
| **Unit tests** | Individual component validation |
| **Integration tests** | Component interaction verification |
| **Contract tests** | MCP protocol compliance verification |
| **Load tests** | Performance under concurrent load (target 99%+ success rate) |

### Automated Testing Patterns
- Use SDK in-memory transports to create client-server pairs in tests (avoids stdio, works in CI)
- Start server as subprocess with stdio, pipe messages, assert on responses
- Use `nock` (TypeScript) or `responses` (Python) to intercept HTTP requests

### Tool Testing with LLMs
- Generate realistic evaluation tasks based on actual use cases
- Measure performance systematically before and after optimizations
- Analyze transcripts to identify rough edges
- Refine tool descriptions based on usage patterns

### Common Debugging Pitfalls
1. **Stdout pollution:** Rogue `console.log` or `print()` on stdout — the #1 cause of mysterious failures
2. Missing capabilities declarations during initialization
3. Unhandled exceptions crashing the server instead of returning structured error results
4. Environment mismatches between development and production
5. Working directory undefined for stdio servers — use absolute paths everywhere

---

## 17. Deployment and Distribution

### Deployment Paths

| Path | Best For |
|------|----------|
| **Remote Streamable HTTP** | Cloud API wrappers. Zero install friction, OAuth support |
| **MCP Apps** | Interactive widgets beyond elicitation's flat-form constraints |
| **MCP Bundles (MCPB)** | Package local server with runtime as single archive for distribution |
| **Local stdio** | Prototyping, with upgrade path to MCPB for distribution |

### Containerization
- Package servers as Docker containers to eliminate environment setup challenges
- Use multi-stage builds with official language images
- Use minimal base images; run containers as non-root with read-only filesystems
- Implement liveness probes and readiness probes
- Set up horizontal pod autoscaling based on CPU/memory thresholds
- Target minimum 3 replicas for availability

### Security Hardening
- Run servers in isolated environments (containers, VMs, sandboxes)
- Apply hardened container configurations; run as non-root users
- Set resource usage limits to prevent infinite loops
- Generate SBOMs per build; sign images and verify at deployment
- Pin dependency versions in lock files; automate vulnerability detection

### VS Code Sandboxing
- Enable sandboxing for locally-running stdio MCP servers to restrict file system and network access
- Sandboxed servers can only access explicitly permitted paths and domains
- Currently macOS and Linux only

### Health Checks
- Database connectivity, cache availability, external API accessibility
- Disk space, memory utilization monitoring
- Response should include overall status, individual check results with response times
- Support `ping` requests for basic health verification

---

## 18. SDK Patterns

### Python SDK (FastMCP)
- `@mcp.tool()` decorator for automatic tool registration and schema generation from type hints
- Docstrings become tool descriptions automatically
- Exceptions in tool functions are automatically converted to MCP error responses
- **Async is essential:** If your tool does any I/O, use `async def`. Synchronous functions block the entire MCP server. Use `httpx.AsyncClient` instead of `requests`.
- **Lifespan pattern:** Use `@asynccontextmanager` for startup/shutdown resource management. Yields a typed `AppContext` available to all handlers.
- **Context object:** `ctx.info()`, `ctx.debug()`, `ctx.report_progress()` for logging and progress within tools
- For larger projects, separate MCP wiring from tool implementations into distinct modules

### TypeScript SDK
- `new McpServer()` with name, version, and capabilities
- Connected via `StdioServerTransport` or HTTP transport
- Built-in request/response handling, automatic timeout management, Zod schema validation
- Use `console.error` (stderr) for logging, never `console.log` (stdout)

### Both SDKs
- Abstract transport complexity, letting developers focus on capability implementation
- Support in-memory transport for unit/integration tests (avoids stdio in CI)
- Handle JSON-RPC compliance, id generation, notification vs request handling automatically

---

## 19. Anti-Patterns to Avoid

### Architecture Anti-Patterns
| Anti-Pattern | Problem |
|-------------|---------|
| **Kitchen Sink / Mega-Server** | Mixing multiple domains and auth boundaries in one server |
| **Bottom-Up API Mirroring** | Exposing raw API endpoints as tools instead of workflow-oriented tools |
| **Universal Router Trap** | Adding MCP as a latency layer to everything including customer-facing paths (300-800ms overhead) |
| **Real-Time Context Delusion** | Putting MCP in checkout flows or trading systems |
| **Stateful Server** | Building servers that cannot horizontally scale |

### Security Anti-Patterns
| Anti-Pattern | Problem |
|-------------|---------|
| Inlining secrets in configurations | Credentials in version control |
| Skipping input validation | Command injection, SQL injection, path traversal |
| Using `eval()` or string concatenation | Code injection, prompt injection |
| Deploying unsigned containers with root access | Full system compromise |
| Omitting audit logging | No forensic trail |
| Approve-once-trust-forever | Silent server behavior changes |
| `npx -y` without version pinning | Supply chain attacks |

### Implementation Anti-Patterns
| Anti-Pattern | Problem |
|-------------|---------|
| Mixed responsibilities | Business logic coupled with MCP infrastructure |
| Overly broad tools | Excessive AI autonomy |
| Silent error swallowing | `except Exception: pass` hides failures |
| Logging to stdout (stdio transport) | Breaks protocol communication |
| No health checks | Crashed backends go undetected |
| Returning protocol errors for tool failures | Should use `isError` flag instead |

### Successful Production Patterns
| Pattern | Description |
|---------|-------------|
| **Intelligence Layer** (Block) | Analyze transactions without touching production |
| **Sidecar** (Zapier) | Enhance workflows without blocking users |
| **Batch** | Process overnight intelligence for morning consumption |
| **Gateway** | stdio locally + Streamable HTTP for cloud capabilities |

---

## Sources

### Official Specification
- [MCP Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25)
- [MCP Tools Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [MCP Lifecycle Specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle)
- [MCP Authorization Specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [MCP Logging Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/logging)
- [MCP Design Principles](https://modelcontextprotocol.io/community/design-principles)

### Anthropic / MCP Official
- [MCP Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- [Writing Effective Tools](https://modelcontextprotocol.info/docs/tutorials/writing-effective-tools/)
- [MCP Debugging Guide](https://modelcontextprotocol.io/docs/tools/debugging)
- [MCP Server Concepts](https://modelcontextprotocol.io/docs/learn/server-concepts)
- [Tool Annotations Blog](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/)

### Microsoft
- [MCP Security Best Practices](https://github.com/microsoft/mcp-for-beginners/blob/main/02-Security/mcp-best-practices.md)
- [Build Your Own MCP Server](https://learn.microsoft.com/en-us/azure/foundry/mcp/build-your-own-mcp-server)

### GitHub
- [Building Your First MCP Server](https://github.blog/ai-and-ml/github-copilot/building-your-first-mcp-server-how-to-extend-ai-tools-with-custom-capabilities/)
- [GitHub Copilot MCP Docs](https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp/set-up-the-github-mcp-server)

### VS Code
- [MCP Developer Guide](https://code.visualstudio.com/api/extension-guides/ai/mcp)
- [Agent Mode Meets MCP](https://code.visualstudio.com/blogs/2025/05/12/agent-mode-meets-mcp)

### Community and Industry
- [Block's Playbook for Designing MCP Servers](https://engineering.block.xyz/blog/blocks-playbook-for-designing-mcp-servers)
- [Klavis AI: Less is More MCP Design Patterns](https://www.klavis.ai/blog/less-is-more-mcp-design-patterns-for-ai-agents)
- [Speakeasy MCP Tool Design](https://www.speakeasy.com/mcp/tool-design)
- [SlowMist MCP Security Checklist](https://github.com/slowmist/MCP-Security-Checklist)
- [cyanheads MCP Server Development Guide](https://github.com/cyanheads/model-context-protocol-resources/blob/main/guides/mcp-server-development-guide.md)
- [lirantal/awesome-mcp-best-practices](https://github.com/lirantal/awesome-mcp-best-practices)
- [modelcontextprotocol.info Best Practices](https://modelcontextprotocol.info/docs/best-practices/)
- [Arcade.dev 54 MCP Tool Patterns](https://blog.arcade.dev/mcp-tool-patterns)
- [MCP Error Codes Reference (mcpevals.io)](https://www.mcpevals.io/blog/mcp-error-codes)
- [MCP Server Observability (Zeo)](https://zeo.org/resources/blog/mcp-server-observability-monitoring-testing-performance-metrics)
- [MCP Observability (Merge)](https://www.merge.dev/blog/mcp-observability)
- [MCP Security Survival Guide (Towards Data Science)](https://towardsdatascience.com/the-mcp-security-survival-guide-best-practices-pitfalls-and-real-world-lessons/)
- [Complete Guide to MCP Security (WorkOS)](https://workos.com/blog/mcp-security-risks-best-practices)
- [Why MCP Deprecated SSE (fka.dev)](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/)
- [MCP Transport Mechanisms (AWS)](https://builder.aws.com/content/35A0IphCeLvYzly9Sw40G1dVNzc/mcp-transport-mechanisms-stdio-vs-streamable-http)

---

Previous: [`protocol-and-operations.md`](protocol-and-operations.md) · Back to [index](README.md)
