# ADR 0003 Exact Rope generation kinds

Date 2026-11-13

Status Accepted

## Context

The MCP generation tool requires exact lowercase kind names. Direct Python callers could pass mixed-case names or surrounding whitespace, and unknown kinds raised a backend error.

## Decision

Require the same exact kind names at the Rope backend and report invalid kinds as input errors.

## Migration

Direct Python callers should pass `class`, `function`, `variable`, `module` or `package`. Catch `ToolInputError` for invalid kinds.
