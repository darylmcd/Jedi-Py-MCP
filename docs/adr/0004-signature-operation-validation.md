# ADR 0004 Signature operation validation

Date 2026-11-17

Status Accepted

## Context

`change_signature` validated `inline_default` targets only when `inline_default` was the first operation. After any earlier operation (`normalize`, `rename`, `reorder`, `add`, `remove`) the has-default and earlier-default checks were skipped, so rope could emit a signature with a required parameter after a defaulted one, such as `def f(a=1, b)`. A `rename` whose `index` was outside the parameter list silently appended a stray parameter, and a `rename` given an explicit `default` could leave a defaulted parameter before a required one.

## Decision

Walk a copy of rope's definition info through the same changers rope will run, in order, and validate each `inline_default` and `rename` against the signature the earlier operations leave. Invalid operations raise `ToolInputError` naming the offending parameter, before any edit is produced.

## Migration

Callers that chained `inline_default` after another operation must inline the earlier defaults first (or in an order that keeps no defaulted parameter before the target). Pass a `rename` `index` inside the parameter list. Give a renamed parameter an explicit `default` only when every later parameter also has one. Catch `ToolInputError` for rejected operations.
