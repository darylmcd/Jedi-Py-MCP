# MCP Best Practices — Design Principles, Server Architecture, Tool Design, Tool Annotations
<!-- purpose: Part 1 of the MCP best-practices reference — see ./README.md for the full index. -->

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

Next: [`validation-and-security.md`](validation-and-security.md) · Back to [index](README.md)
