# MCP Best Practices — Input Validation, Error Handling, Security, Auth
<!-- purpose: Part 2 of the MCP best-practices reference — see ./README.md for the full index. -->

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

Previous: [`design-and-architecture.md`](design-and-architecture.md) · Next: [`protocol-and-operations.md`](protocol-and-operations.md) · Back to [index](README.md)
