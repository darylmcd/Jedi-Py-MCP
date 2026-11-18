# ADR 0004 Signature operation validation

Date 2026-11-17

Status Accepted

## Context

`change_signature` validated `inline_default` targets only when `inline_default` was the first operation. After any earlier operation (`normalize`, `rename`, `reorder`, `add`, `remove`) the has-default and earlier-default checks were skipped, so rope could emit a signature with a required parameter after a defaulted one, such as `def f(a=1, b)`.

## Decision

Walk a copy of rope's definition info through the same changers rope will run, in order, and validate each `inline_default` against the signature the earlier operations leave. Invalid operations raise `ToolInputError` naming the offending parameter, before any edit is produced.

## Migration

Callers that chained `inline_default` after another operation must inline the earlier defaults first (or in an order that keeps no defaulted parameter before the target). Catch `ToolInputError` for rejected operations.

## Addendum: rename operation (rope-signature-rename-bindings)

### Context

`rename` was a rope `ArgumentRemover` plus `ArgumentAdder`: call arguments for the parameter and its default were lost, and the function body kept the old name.

### Decision

- `rename` is an in-place changer: position, default and call arguments are kept (an explicit `default` replaces the default).
- A body pass (`util/param_rename.py`) renames the parameter's bindings in the definition. An AST generator proposes the `Name` spans; the compiled code objects of the original and the result are compared instruction by instruction (names may differ only as the requested renames, for the parameter's own variable). Anything it cannot prove raises `ToolInputError` before any edit is written; there is no partial rename.
- `change_signature` refuses `async def` targets for every operation: rope produces no edit, or drops the parameter, for them.
- rope drops parameter annotations on every operation and keeps the return annotation; the tool-layer post-pass restores them.
- Known benign over-refusals (fail-closed): a parameter named like a module-level import, a comprehension that reuses the parameter name, f-string `=` and t-string text, class-body annotations under `from __future__ import annotations`, private-name mangling.

### Migration

Newly rejected with `ToolInputError`: a rename index out of range, a new name that is not an NFKC-normal identifier or duplicates another parameter, an explicit rename default before a required parameter, rename cycles, renames the body pass cannot prove (nonlocal, rebinding by import/def/except/match, dynamic frame access, new name already used in the function, keyword-only functions), and any operation on an async function. Callers must rename such parameters by hand or in separate steps.
