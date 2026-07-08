# MCP Best Practices — Transport, Resources, Prompts, Sampling, Performance, Logging, Lifecycle
<!-- purpose: Part 3 of the MCP best-practices reference — see ./README.md for the full index. -->

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

Previous: [`validation-and-security.md`](validation-and-security.md) · Next: [`testing-deployment-and-patterns.md`](testing-deployment-and-patterns.md) · Back to [index](README.md)
