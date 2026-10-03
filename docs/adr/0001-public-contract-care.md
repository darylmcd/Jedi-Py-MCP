# ADR 0001: Public contract-care mode

Date: 2026-10-01 (recorded here on 2026-10-02)

Status: Accepted operator decision

## Context

Jedi-Py-MCP is public on GitHub and is not published on PyPI. The earlier 2026-09-24 ruling permitted breaking tool-contract corrections without an ADR or migration note. The current canonical operator guidance in `~/.claude/CLAUDE.md`, Standing Directive #4, records the 2026-10-01 decision that this repository stays public and follows contract-care requirements like Roslyn-Backed-MCP.

## Decision

Treat the repository as public and in contract-care mode. Breaking changes require an ADR and a migration note in the changelog. Tool or parameter removals, renames, and newly rejected input must also be called out in the PR body and use the existing `changed-breaking-*` changelog fragment convention. The October 1 decision supersedes the September 24 ADR/migration exemption.

## Consequences

Correctness remains the priority. When correcting a public contract requires a breaking change, record the rationale, explain the consumer migration and apply the repository's versioning and deprecation policy. Public status does not require retaining an incorrect implementation through compatibility shims.

This record changes instruction policy only; it does not change a tool contract or claim that release automation has been updated.
