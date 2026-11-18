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

### Limits of the rename check

The refusals are not a complete guarantee. The compiled-code comparison proves the variable binding; it cannot see name-based access to it:

- Refused: `locals`, `vars`, `eval`, `exec`, `dir`, `_getframe`, `currentframe`, `getargvalues`, `stack` (as names or attributes) and `f_locals`.
- Not detected: an alias (`ev = eval`), `functools.partial(f, b=2)` and `**{'b': ...}` callers, `f.__code__.co_varnames`, `inspect.signature`, `__annotations__`, and subclass overrides (rope does not rename them, so keyword calls through the base break).
- Same-name definitions: rope rewrites the header of every definition it resolves to the target (a redefinition, conditional `def`, `@overload` stub, property setter), but only the target's body is renamed; such a rename is refused. Same-named methods of different classes are not rewritten by rope (observed) and are not refused.

- NFKC widening: the shared `validate_identifier` now also rejects non-NFKC names at the tool boundary for: `base_class_name`, `class_name`, `collaborator_attribute`, `destination_attr`, `new_name`, `new_class_name`, `function_name`, `method_name`, `variable_name`, `parameter_name`, `factory_name`, `classname`, `protocol_name`, `symbol_name`, the list parameters `class_names` and `members` (including the same parameters inside `refactor_transaction` steps), and each segment of `package_name` (`create_type_stubs`). Use the NFKC spelling (`unicodedata.normalize("NFKC", name)`).

## Addendum: add and reorder default order (signature-add-reorder-default-order-validation)

### Context

`add` and `reorder` could leave a required parameter after a defaulted one (`def f(a=1, b)`, `def f(b=2, a)`), and `reorder` accepted a `new_order` that is not a permutation: a duplicate index wrote `def f(a, a)`, a short list dropped a parameter, an out-of-range index raised a generic `RopeError`. Separately, rope mangles a definition with `*args`: `DefinitionInfo.read` reads `def f(a, b=1, *args)` with `b` required and a `*args` entry, and the emitted header is unparseable (`def f(a, b, *args=1)`).

### Decision

- `change_signature` refuses every operation on a target with `*args` (`ToolInputError`, `parameter: line`, decided from the definition's AST). rope cannot rewrite such a header: it emits an unparseable `*args=<default>` (`def f(a, b=1, *args)` + `inline_default` previews `def f(a, b, *args=1)`) and shifts the defaults before `*args`, so no check on its parameter list can make the result valid. A bare `*` (keyword-only parameters) is not refused here; its broken emission (`def f(a, *, k=1)` + `add` previews `def f(a, c, *)`) stays with the keyword-only row.
- The simulated walk takes the positional parameters and their defaults from the target definition's AST, not from rope's `DefinitionInfo` (keyword-only parameters are not listed).
- After the walk, the FINAL signature must not hold a required parameter after a defaulted one. Only the final state is checked because rope emits only that: `add` a required parameter then `reorder` it before the default, or `add` then `remove` the default, is valid. The error names the last `add` or `reorder` operation that placed either parameter (`operations[i].default` or `operations[i].new_order`).
- `reorder.new_order` must be a permutation of the positional parameter indexes (`ToolInputError`, `operations[i].new_order`).
- Unchanged and out of scope: `_check_rename_default` still checks per step; add-name validity (duplicate or invalid identifier) belongs to the identifier validators; keyword-only and positional-only separators are handled by other rows.

### Migration

Newly rejected with `ToolInputError`: every operation on a function that has `*args` (previously `inline_default` was refused for the wrong reason and the other operations produced unparseable code; change such a function by hand); an `add` or `reorder` whose final signature has a required parameter after a defaulted one (give the added parameter a default, place it before the first defaulted parameter, or order defaulted parameters last), and a `reorder` whose `new_order` is not a permutation of `0..n-1` over the positional parameters (`self` counts for methods). Callers must pass one index per positional parameter, each once.

## Addendum: typed errors for rope signature failures (rope-signature-generic-ropeerror)

### Context

Three caller-input failures surfaced as a generic `RopeError` (`ROPE_BACKEND`, "rope.change_signature failed: ..."), nothing written: a position that is not a `def` function (a lambda, a class without `__init__`, a variable, a module: rope's `RefactoringError` in the `ChangeSignature` constructor); a call site that passes `**kwargs` to the target (rope's `assert kw.arg`); and a non-NFKC identifier in the workspace (rope's `MismatchedTokenError`: `ast.parse` NFKC-normalises identifiers, so the patched AST cannot match the raw token).

### Decision

- Translate on failure with a positive diagnosis; never pre-reject. rope fails only for the modules it patches and only for calls it resolves to the target, so no static scan is exact: a pre-flight scan would newly refuse workspaces rope handles today (a non-NFKC identifier in an unrelated file, a `**` call to another function of the same name, a non-NFKC name in a comment).
- Non-function target: the constructor's only `RefactoringError` becomes `ToolInputError` ("target must be a def function").
- Non-NFKC identifier (constructor or `get_changes`): after the `MismatchedTokenError`, tokenize the workspace Python files; a `ToolInputError` names up to five `path:line` sites. No site found: the original error propagates unchanged.
- `**` call site (`AssertionError` from `get_changes` only): after the failure, find `ast.Call` nodes with a `**` keyword whose callee name is the target (or its class for `__init__`); a `ToolInputError` names the sites. No site found: the original error propagates unchanged.
- Limits: the `**` attribution is by callee name, so it can name a call to an unrelated function of the same name, and an unrelated assertion inside `get_changes` can be mislabelled when such a call exists; the diagnosis runs only after rope failed and nothing was written. Under `python -O` rope's assert is stripped and the `**` path is not reached. The non-NFKC attribution can likewise mislabel a different `MismatchedTokenError` when a non-NFKC identifier exists elsewhere in the workspace.
- Out of scope: other rope tools raise the same errors for the same inputs (a non-NFKC workspace fails every rope refactoring); keyword-only emission stays with `rope-signature-override-and-kwonly-gaps`.

### Migration

No input changes validity; these inputs already failed. The error is now `ToolInputError` (`[INVALID_INPUT]`, message names the cause and `path:line`) instead of the backend error `ROPE_BACKEND`. Clients that matched the backend code or retried on it must match `INVALID_INPUT`: point the call at a `def` function, pass call-site arguments explicitly instead of `**`, or use the NFKC spelling of identifiers.
