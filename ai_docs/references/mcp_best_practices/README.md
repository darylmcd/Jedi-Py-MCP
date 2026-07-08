# MCP Server Implementation Best Practices
<!-- purpose: Index for the canonical MCP server design/security/performance/operations reference, split by topic. -->

**Purpose:** Canonical reference for MCP server design, security, performance, and operations — applicable to any MCP server implementation.

**Last Updated:** 2026-03-28

**Sources:** Anthropic (modelcontextprotocol.io), Microsoft, GitHub, VS Code, Block, Klavis AI, Speakeasy, SlowMist, community best practices. Full source list in [`testing-deployment-and-patterns.md`](testing-deployment-and-patterns.md#sources).

Split into four topic files (each was one section range of the prior single-file version) to stay under the `ai_docs/references/*` size cap:

| File | Covers |
|---|---|
| [`design-and-architecture.md`](design-and-architecture.md) | Design Principles · Server Architecture · Tool Design · Tool Annotations |
| [`validation-and-security.md`](validation-and-security.md) | Input Validation & Schema Design · Error Handling · Security · Authentication and Authorization |
| [`protocol-and-operations.md`](protocol-and-operations.md) | Transport Mechanisms · Resource Management · Prompt Design · Sampling · Performance · Logging and Observability · Lifecycle Management |
| [`testing-deployment-and-patterns.md`](testing-deployment-and-patterns.md) | Testing and Debugging · Deployment and Distribution · SDK Patterns · Anti-Patterns to Avoid · Sources |
