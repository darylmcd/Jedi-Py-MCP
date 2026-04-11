# MCP Server Implementation Best Practices
<!-- purpose: Canonical reference for MCP server design, security, performance, and operations. -->

**Purpose:** Canonical reference for MCP server design, security, performance, and operations — applicable to any MCP server implementation.

**Last Updated:** 2026-03-28

**Sources:** Anthropic (modelcontextprotocol.io), Microsoft, GitHub, VS Code, Block, Klavis AI, Speakeasy, SlowMist, community best practices. Full source list at end of document.

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [Server Architecture](#2-server-architecture)
3. [Tool Design](#3-tool-design)
4. [Tool Annotations](#4-tool-annotations)
5. [Input Validation and Schema Design](#5-input-validation-and-schema-design)
6. [Error Handling](#6-error-handling)
7. [Security](#7-security)
8. [Authentication and Authorization](#8-authentication-and-authorization)
9. [Transport Mechanisms](#9-transport-mechanisms)
10. [Resource Management](#10-resource-management)
11. [Prompt Design](#11-prompt-design)
12. [Sampling](#12-sampling)
13. [Performance](#13-performance)
14. [Logging and Observability](#14-logging-and-observability)
15. [Lifecycle Management](#15-lifecycle-management)
16. [Testing and Debugging](#16-testing-and-debugging)
17. [Deployment and Distribution](#17-deployment-and-distribution)
18. [SDK Patterns](#18-sdk-patterns)
19. [Anti-Patterns to Avoid](#19-anti-patterns-to-avoid)

---

## 1. Design Principles

The MCP governance model establishes these core principles (from modelcontextprotocol.io):

| Principle | Meaning |
|-----------|---------|
| **Convergence over choice** | One well-designed path per problem, not many alternatives |
| **Composability over specificity** | Build on primitives (resources, tools, prompts); don't add protocol features for use cases constructible from existing blocks |
| **Interoperability over optimization** | Favor features that degrade gracefully; use capability negotiation |
| **Stability over velocity** | Every addition is permanent; optimize for decades not quarters |
| **Capability over compensation** | Avoid permanent structure to work around temporary model limitations |
| **Demonstration over deliberation** | Working implementations over theoretical debates |
| **Pragmatism over purity** | Practical tradeoffs for adoption and usability |
| **Standardization over innovation** | Codify proven patterns rather than inventing new paradigms |

---

## 2. Server Architecture

### Single Responsibility
Each MCP server should have one clear, well-defined purpose. This enables independent scaling, failure isolation, and clear ownership boundaries. Avoid the "kitchen sink" anti-pattern of mixing multiple domains and auth boundaries in one server.

### Layered Architecture
Separate concerns into distinct layers:
- **MCP registration layer** (server.py) — protocol handling, tool registration
- **Orchestration layer** (tools/) — business logic, backend coordination
- **Backend I/O layer** (backends/) — external service communication

Use protocol-based decoupling so tools never import backend classes directly. Define Protocol classes for testability and loose coupling.

### Inversion of Control
Pass a server object to capabilities rather than having capabilities reach for global state. This enables flexibility across transport types and deployment platforms.

### Fail-Safe Design
- Implement circuit breakers with configurable thresholds
- Use multi-level caching strategies (in-memory, persistent)
- Apply rate limiting with token bucket algorithms
- Provide safe default responses during failures
- Enable fallback to cached data when backends are unavailable

---

## 3. Tool Design

### Workflow-First Design
Design top-down from user workflows, not bottom-up from API endpoints. Combine multiple internal calls into single high-level tools that serve actual user tasks.

**Cautionary example (Block):** v1 of their Linear MCP had 30+ granular tools mirroring GraphQL endpoints, requiring 4-6 chained calls for simple questions. v3 collapsed to two universal query tools.

### Tool Count
More tools do not always lead to better outcomes. LLMs become unreliable when exposed to more than 30-40 tools. Consider progressive discovery or semantic search patterns for large tool sets.

### Four Key Design Patterns (Klavis AI)

| Pattern | When to Use |
|---------|-------------|
| **Semantic Search** | Large tool sets with distinct purposes — dynamically retrieve relevant tools via vector similarity |
| **Workflow-Based** | Well-defined, repeated workflows — atomic self-contained operations |
| **Code Mode** | Data processing and batch operations — agents write complete programs in secure sandboxes |
| **Progressive Discovery** | Extensive catalogs — guide agents through discovery stages |

### Naming Conventions
- Use `snake_case` with `{verb}_{noun}` pattern for tool names (e.g., `generate_report`, `fetch_data`)
- Use `camelCase` for tool parameters (e.g., `queryString`, `userId`)
- Be consistent — mixed conventions force LLMs to memorize individual names rather than predicting them
- Namespace related tools under common prefixes (e.g., `asana_projects_search`)
- Avoid spaces, dot notation, brackets, or parentheses in tool names
- Use unambiguous parameter names like `user_id` instead of vague `user`

### Description Best Practices
- Write descriptions explaining **when and how** to use tools within larger workflows, not just technical details
- Include use-case examples and important operational notes
- Call out alternative naming conventions and synonyms to help LLM recognition
- Make implicit context explicit: specialized query formats, terminology, resource relationships
- Think of how you would describe the tool to a new hire
- Tool descriptions have a **greater impact than model choice** on quality

### Response Design
- Implement pagination, range selection, filtering, and truncation with sensible defaults
- Support dual response modes: "detailed" for comprehensive data and "concise" for token efficiency
- Return only high-signal information
- Avoid "not found" responses — present relevant alternatives. LLMs are overly influenced by negative statements
- Exception: prioritize security and privacy when handling sensitive user data

### Interaction Model
- Tools are **model-controlled** — the LLM discovers and invokes them automatically
- There SHOULD always be a human in the loop with the ability to deny tool invocations
- Applications SHOULD provide UI making clear which tools are exposed to the AI model
- Applications SHOULD present confirmation prompts for destructive operations

---

## 4. Tool Annotations

### Annotation Fields (MCP Spec 2025-03-26+)

| Field | Default | Meaning |
|-------|---------|---------|
| `title` | — | Human-readable display name for UIs |
| `readOnlyHint` | `false` | Tool does not modify its environment |
| `destructiveHint` | `true` | Modifications are destructive vs. additive |
| `idempotentHint` | `false` | Safe to call repeatedly with same arguments |
| `openWorldHint` | `true` | Interacts with external entities vs. closed domain |

### Implementation Guidance
- Mark read-only operations with `readOnlyHint: true` — VS Code skips confirmation dialogs for these
- Set `destructiveHint: false` for additive-only changes
- Use `openWorldHint: false` for closed-domain tools with no external data sources
- `destructiveHint` and `idempotentHint` are only meaningful when `readOnlyHint` is false
- Defaults are pessimistic (assume worst-case) when annotations are absent

### Trust Model
- Annotations are **hints, not guarantees**
- Clients MUST treat annotations as untrusted unless they come from a trusted server
- Malicious servers can claim `readOnlyHint: true` while deleting files

### The "Lethal Trifecta" Warning
Sessions mixing these three capabilities create data exfiltration vulnerabilities:
1. Access to private data
2. Exposure to untrusted content
3. Ability to communicate externally

Annotations on individual tools cannot reveal these dangerous combinations — clients must reason across session context.

---

## 5. Input Validation and Schema Design

### Schema Requirements
- Define clear schemas using JSON Schema or validation libraries (Zod for TypeScript, Pydantic for Python)
- All inputs/outputs should use typed models for validation, serialization, and documentation in one layer
- Every parameter should have a `description` field
- Specify `required` vs optional parameters explicitly
- Use `enum` for constrained values
- Provide `default` values for optional parameters

### Parameter Design for LLMs
- Omit low-level technical identifiers (UUIDs, MIME types, pixel dimensions)
- Favor semantic identifiers: use `name`, `image_url`, `file_type` over cryptic codes
- Implement parameter coercion: accept "2024-01-15", "January 15", or "yesterday" and normalize internally
- Resolving alphanumeric UUIDs to semantically meaningful language significantly improves agent precision

### Validation Checklist
- Validate all tool inputs before processing
- Validate workspace paths to prevent path traversal attacks
- Validate string parameters that should be valid identifiers
- Validate enum-like string parameters against known valid values
- Implement file size checks before processing (Block uses 400KB limit with actionable error messages)
- Use allowlists for file paths, database names, and command arguments

### Output Schema
- When providing an `outputSchema`, servers MUST return structured results conforming to the schema
- For backwards compatibility, tools returning structured content SHOULD also return serialized JSON in a TextContent block
- Clients SHOULD validate structured results against output schemas

---

## 6. Error Handling

### Three-Tier Error Model

| Tier | Scope | Examples |
|------|-------|---------|
| **Transport** | Network/connection failures | Timeouts, broken pipes, auth failures |
| **Protocol** | JSON-RPC 2.0 violations | Malformed JSON, non-existent methods, invalid parameters |
| **Application** | Tool execution failures | API failures, invalid input data, business logic errors |

### Standard JSON-RPC Error Codes

| Code | Name | Meaning |
|------|------|---------|
| -32700 | Parse Error | Invalid JSON syntax |
| -32600 | Invalid Request | Valid JSON but wrong protocol structure |
| -32601 | Method Not Found | Operation does not exist |
| -32602 | Invalid Params | Arguments don't meet requirements |
| -32603 | Internal Error | Server-side execution failure |
| -32800 | Request Cancelled | Request was cancelled |
| -32801 | Content Too Large | Content exceeds limits |
| -32000 to -32099 | Server Error | Implementation-specific |

### Key Distinction: Tool Errors vs Protocol Errors
Failed tool calls return a **successful JSON-RPC response** with `isError: true` in the result — NOT a JSON-RPC error object. This separates protocol errors from application errors.

### Error Messages for Agents
Errors should teach, not just fail. Provide actionable guidance:
- **Bad:** Raw 429 status code
- **Good:** "Rate limited. Retry after 30 seconds or reduce batch size to 50."
- Include examples of correct input formatting in error responses
- Include retry guidance (`retry_after`) for transient failures

### Error Handling Patterns
- Convert all backend-specific errors to a consistent error type for MCP consumers
- Preserve original stack traces when re-raising errors (use `from exc`)
- Sanitize error messages to prevent information leakage
- Never use bare `except Exception: pass` — always log at minimum DEBUG level
- Implement graceful degradation when capabilities fail
- Handle connection interruptions with reconnection logic

---

## 7. Security

### Input Sanitization
- Never pass user-supplied input directly to shell commands, database queries, or file system operations
- Build parameterized queries instead of string concatenation
- Sanitize strings: escape shell characters, enforce length limits
- Use allowlists; reject unexpected input rather than trying to sanitize it

### Path Traversal Prevention
- Validate that all file paths are within the workspace boundary
- Call path validation on **every** tool that accepts `file_path`, `source_file`, or `destination_file`
- A `validate_workspace_path()` function that exists but is never called is a security gap, not a security feature

### Real-World Vulnerability Data (2025-2026)
- **43% of early MCP servers** contained command injection vulnerabilities (Invariant Labs audit)
- Anthropic's reference SQLite MCP server had SQL injection morphing into prompt injection — forked 5,000+ times before archival
- Anthropic's Git MCP server allowed path traversal and arbitrary command execution
- ~2,000 internet-exposed MCP servers scanned by Knostic — all lacked any authentication

### Server Security Requirements (from MCP spec)
- MUST validate all tool inputs
- MUST implement proper access controls
- MUST rate limit tool invocations
- MUST sanitize tool outputs
- MUST validate all resource URIs
- MUST check resource permissions before operations
- MUST NOT accept tokens not explicitly issued for the MCP server
- Binary data MUST be properly encoded

### Client Security Expectations
- SHOULD prompt for user confirmation on sensitive operations
- SHOULD show tool inputs to the user before calling the server (prevents data exfiltration)
- SHOULD validate tool results before passing to LLM
- SHOULD implement timeouts for tool calls
- SHOULD log tool usage for audit purposes

### Prompt Injection Defense
- Deploy prompt shields with spotlighting, delimiters, and datamarking
- Validate tool metadata, monitor for changes, verify integrity
- Scan model outputs for data leakage, harmful content, or policy violations
- Do not directly insert returned data into context without verification

### Supply Chain Security
- `npx -y package-name` fetches latest from npm with zero verification — pin versions explicitly
- Never commit `mcp.json` with API keys to git; use environment variable references
- The trust model in most MCP clients is approve-once-trust-forever — if a server updates remotely, the client won't notice
- Verify provenance, integrity, and security of all components
- Use digital signatures or checksums to prevent tampering

### SSRF Prevention (for clients)
- Require HTTPS for all OAuth-related URLs in production
- Block requests to private/reserved IP ranges
- Validate redirect targets with same restrictions
- Be aware of TOCTOU issues with DNS-based validation

### Multi-Server Isolation
- Ensure operational isolation among multiple MCP servers
- Assign each server clear resource access boundaries
- Use distinct permission sets for different domain tools
- Enforce strict namespace isolation

---

## 8. Authentication and Authorization

### OAuth Requirements
- OAuth 2.1 is mandatory for HTTP-based transports (March 2025 spec revision)
- November 2025 revision added client-credentials flow for M2M authentication
- MUST implement PKCE for authorization code flows
- Access tokens MUST NOT be included in URI query strings
- Authorization MUST be included in every HTTP request
- Use short-lived access tokens with secure rotation and audience validation

### Discovery Endpoints
Always implement:
- `/.well-known/oauth-protected-resource`
- `/.well-known/oauth-authorization-server`

Clients fail silently without these.

### Credential Management
- Store credentials in environment variables, never in code
- Use secure vault systems (Azure Key Vault, AWS Secrets Manager, HashiCorp Vault)
- Use `${input:}` syntax in VS Code to prompt for tokens at startup
- Rotate API keys and credentials periodically
- Never log tokens or pass them in URLs

### Session Management
- Generate session IDs using cryptographically secure random generators
- Format: `<user_id>:<session_id>` for user-specific binding
- Implement proper session expiration, rotation, and invalidation
- MUST NOT use sessions for authentication

### Scope Minimization
- Start with minimal initial scope containing only low-risk operations
- Use incremental elevation via targeted challenges
- Server should accept reduced-scope tokens
- Avoid wildcard or omnibus scopes
- Log elevation events with correlation IDs

---

## 9. Transport Mechanisms

### Rule of Thumb
If the user controls the machine the server runs on, use **stdio**. Otherwise, use **Streamable HTTP**.

### stdio
- Client launches MCP server as a subprocess
- Messages delimited by newlines; MUST NOT contain embedded newlines
- Server MUST NOT write anything to stdout that is not a valid MCP message
- Server MAY write UTF-8 strings to stderr for logging
- Clients SHOULD support stdio whenever possible
- Shutdown sequence: close stdin → wait → SIGTERM → SIGKILL

### Streamable HTTP (the modern standard, replaces SSE)
- Single HTTP endpoint supporting POST and GET
- Server dynamically chooses between immediate JSON responses or SSE streaming per request
- MUST validate the `Origin` header on all incoming connections (DNS rebinding prevention)
- When running locally, SHOULD bind only to localhost (127.0.0.1), not 0.0.0.0
- Client MUST include `Accept` header listing both `application/json` and `text/event-stream`
- Client MUST include `MCP-Protocol-Version` header on all subsequent requests
- Supports session management via `Mcp-Session-Id` header
- Supports resumability via SSE `id` fields and `Last-Event-ID` header

### SSE (deprecated)
- Required persistent connections and two separate endpoints
- Prevented serverless scaling; forced tokens into URL query strings
- Replaced by Streamable HTTP in 2025-03-26 spec

### Backward Compatibility Detection
POST an InitializeRequest to the server URL: if it succeeds, assume Streamable HTTP. If 400/404/405, issue GET expecting SSE stream. When the endpoint event arrives, assume legacy HTTP+SSE.

### Gateway Pattern
Many production architectures use both transports: stdio locally for file system access, connecting upstream to Streamable HTTP servers for cloud capabilities.

---

## 10. Resource Management

### Resource Design
- Each resource uniquely identified by a URI
- Resources are **application-driven** (host decides how to incorporate context)
- Include `name`, optional `title`, `description`, `mimeType`, `size`
- Use annotations: `audience`, `priority` (0.0-1.0), `lastModified` (ISO 8601)

### URI Schemes
- `https://` — only when client can fetch directly from the web
- `file://` — filesystem-like resources (need not be actual filesystem)
- `git://` — version control integration
- Custom schemes MUST conform to RFC 3986

### Resource Templates
- Use URI templates (RFC 6570) for parameterized resources
- Support parameter auto-completion via the completion API
- Include metadata (title, description, mimeType) for discoverability

### Subscriptions
- Support optional subscriptions to resource changes
- Emit `notifications/resources/updated` when subscribed resources change
- Emit `notifications/resources/list_changed` when available resources change

---

## 11. Prompt Design

### Structure
- Prompts are **user-controlled** — require explicit invocation, not automatic triggering
- Include `name` (unique identifier), optional `title`, `description`, `arguments`
- Arguments support auto-completion via the completion API
- Messages can contain text, image, audio, and embedded resources
- Image and audio data MUST be base64-encoded with valid MIME type

### Implementation
- Servers SHOULD validate prompt arguments before processing
- Clients SHOULD handle pagination for large prompt lists
- MUST validate all prompt inputs and outputs to prevent injection attacks

---

## 12. Sampling

### Design
- Sampling allows servers to request LLM completions from clients
- Clients maintain control over model access, selection, and permissions
- No server API keys necessary
- There SHOULD always be a human in the loop

### Model Preferences
- Use abstract capability priorities (0-1): `costPriority`, `speedPriority`, `intelligencePriority`
- Provide model `hints` as substring matches for flexible model selection
- Hints are advisory — clients make final model selection
- Clients MAY map hints to equivalent models from different providers

### Security
- Clients SHOULD implement user approval controls
- Both parties SHOULD validate message content
- Clients SHOULD implement rate limiting
- Applications SHOULD provide UI for reviewing sampling requests

---

## 13. Performance

### Caching
- Cache read-heavy operations with appropriate TTLs
- Pre-warm connections and reuse HTTP clients with configured timeouts
- Cache static resources and capability definitions

### Concurrency
- Use concurrent execution for workspace-wide operations (e.g., `asyncio.gather` for file scanning)
- Avoid sequential iteration over all workspace files for operations like diagnostics
- Implement concurrency guards on expensive workspace-wide scans

### Timeouts
- SHOULD establish timeouts for all sent requests
- When timeout expires, SHOULD issue cancellation notification and stop waiting
- SDKs SHOULD allow per-request timeout configuration
- MAY reset timeout clock on progress notifications
- SHOULD always enforce maximum timeout regardless of progress notifications

### Pagination
- `tools/list`, `resources/list`, `resources/templates/list`, and `prompts/list` all support cursor-based pagination
- Clients SHOULD handle pagination for large lists

### Output Management
- Implement `limit` parameters on tools that can return large result sets
- Truncate large payloads to avoid overwhelming LLM context
- Consider summary modes for workspace-wide operations to reduce token overhead

### Long-Running Operations
- Return handles for long-running operations; support polling via status tools
- Use `notifications/progress` messages to keep clients informed
- Implement cancellation support via `$/cancelRequest` notifications
- Make tool calls idempotent — accept client-generated request IDs, return deterministic results

### Performance KPIs (modelcontextprotocol.info)
- Throughput: >1000 requests/second per instance
- Latency P50: <100ms for simple operations
- Latency P99: <500ms for complex operations
- Error rate: <0.1% under normal conditions
- Availability: >99.9% uptime

---

## 14. Logging and Observability

### Logging
- **stdio transport:** Write to stderr ONLY. Never write non-MCP content to stdout. In JavaScript, use `console.error` (stderr), never `console.log`. This is the #1 cause of mysterious MCP server failures.
- **HTTP transport:** Use `notifications/message` mechanism, server-side aggregation, or HTTP tooling
- Servers that emit log messages MUST declare the `logging` capability
- Clients can adjust minimum level at runtime via `logging/setLevel`
- Use structured JSON logs with correlation IDs for traceability

### Log Levels (RFC 5424)
`debug`, `info`, `notice`, `warning`, `error`, `critical`, `alert`, `emergency`

### What to Log
- Initialization steps and capability negotiation
- Resource access and tool execution
- Error conditions with stack traces and context
- Performance metrics (operation timing, resource usage, message sizes, latency)
- Request IDs for correlation

### What NOT to Log
- Credentials or secrets
- Personal identifying information
- Internal system details that could aid attacks

### Observability
- Track tool success rates, latency (p95), error classes, and policy denials
- OpenTelemetry trace/span model maps well to agent behavior
- MCP supports context propagation through `_meta` field using W3C Trace Context format
- Tools: OpenTelemetry, Datadog LLM Observability, Langfuse MCP Tracing, Arize Phoenix, MCPcat

### Audit
- Implement detailed, searchable audit logs for all MCP operations and security events
- Capture structured audit trails: who, what, when, why — with argument redaction for sensitive data
- Detect and report anomalous activity patterns
- Centralize logs; prevent log tampering

---

## 15. Lifecycle Management

### Initialization (MUST be first interaction)
1. Client sends `initialize` request with protocol version, capabilities, client info
2. Server responds with its capabilities and information
3. Client sends `initialized` notification
4. Client SHOULD NOT send requests (other than pings) before server responds
5. Server SHOULD NOT send requests (other than pings and logging) before receiving initialized notification

### Version Negotiation
- Client sends protocol version (SHOULD be latest supported)
- If server supports it, MUST respond with same version
- Otherwise server MUST respond with another supported version
- If client doesn't support server's version, SHOULD disconnect

### Capability Negotiation
- Both parties MUST respect negotiated protocol version
- Only use capabilities that were successfully negotiated
- **Server capabilities:** prompts, resources, tools, logging, completions
- **Client capabilities:** roots, sampling, elicitation

### Dynamic Updates
- Servers can change available tools on the fly via `notifications/tools/list_changed`
- Show different actions as workflows progress, or surface tools relevant to detected frameworks

### Shutdown
- **stdio:** Close stdin → wait → SIGTERM → SIGKILL
- **HTTP:** Close associated HTTP connections, send HTTP DELETE for session termination

### Specification Timeline
| Version | Key Changes |
|---------|-------------|
| 2024-11-05 | Initial spec; defined stdio and SSE transports |
| 2025-03-26 | Streamable HTTP introduced; SSE deprecated; OAuth 2.1 added; tool annotations |
| 2025-06-18 | SSE formally replaced by Streamable HTTP |
| 2025-11-25 | Current spec; adds OAuth client-credentials flow for M2M auth |

---

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
