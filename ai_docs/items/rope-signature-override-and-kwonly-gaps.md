# rope-signature-override-and-kwonly-gaps — change_signature: change the whole override family or refuse

**row:** `rope-signature-override-and-kwonly-gaps` · **pri:** `Low` · **size:** `L`

## Anchors

- `src/python_refactor_mcp/backends/rope_backend.py:1311`
- `src/python_refactor_mcp/backends/rope_backend.py:1341`
- `docs/adr/0004-signature-operation-validation.md`

## Acceptance

Operator decision 2026-11-18: hierarchy-wide or refuse; never refuse base-side methods outright. Rule: change the complete override family or change nothing. "Override family" = a method, every method it overrides and every method that overrides it, across the project. Applies to every signature operation (rename, add, remove, reorder, inline default). This table is the acceptance:

| # | Target | Required behaviour |
|---|---|---|
| 1 | Method with no override family | Unchanged: change it and its call sites. |
| 2 | Family member, called on the base-side member | Apply the change to every member and all call sites (in_hierarchy=True). |
| 3 | Family member, called on a derived-side member | Same as 2; derived-side is not exempt. |
| 4 | `__init__` and `__new__` | Change that one class only, as today (derived `__init__` calling `super().__init__` stays correct). |
| 5 | Any member's parameter list differs from the target's in a position or name the operation touches | Typed refusal naming the class and method that differ. |
| 6 | A class in the hierarchy rebinds the name by class-body assignment (`m = lambda`, `m = other`, `m = partial(...)`) | Typed refusal naming the class. |
| 7 | Dynamic overrides (`type(...)` dicts, `setattr`, metaclass injection, runtime monkey-patching) | Documented limit in the ADR: a known false negative. |
| 8 | Family cannot be fully enumerated (unresolvable base, base outside the workspace or in an installed package) | Typed refusal saying which base could not be resolved; never a partial family. |

Tests, each red on current main:

- [ ] Cases 2 and 3: three-level hierarchy; every member and every call site (through base and derived types) is updated and the module still imports and runs.
- [ ] Case 4: derived `__init__` changed alone; base `__init__` untouched.
- [ ] Case 5: one overrider has an extra or renamed parameter in an affected position; typed refusal and no file changed.
- [ ] Case 6: subclass body rebinds the name by assignment; typed refusal and no file changed.
- [ ] Case 8: base class from outside the workspace; typed refusal.
- [ ] One test per operation kind (rename, add, remove, reorder) for case 2; inline default covered too.
- [ ] ADR (extend 0004 or add a new one) plus a `changed-breaking-*` changelog fragment and PR-body callout: the same call now edits more files; cases 5, 6 and 8 are new refusals; case 7 is the documented limit.

## Evidence

- rope's `ChangeSignature.get_changes(changers, in_hierarchy=False, ...)` can apply changers across the hierarchy; src/ never passes `in_hierarchy` (`rope_backend.py:1341`), so only one method and its call sites change and the rest of its family is left untouched.
- Keyword-only and positional-only refusals shipped in #224 and are out of this row; the remaining keyword-only gap is `introduce-inline-parameter-kwonly`.

## Notes

2026-11-18 operator decision (unblocks the row). Verify before relying on rope, both untested by the operator: (1) how rope behaves when family members' signatures differ; expected: it applies the same change blindly, so the case 5 check must run before `get_changes`, not after. (2) How completely `in_hierarchy` finds subclasses across files and packages of one workspace; if it misses any, enumerate the family yourself and treat every member rope would not touch as case 8. Ordering: case 5/6/8 checks run before `get_changes`; the family enumeration is one helper shared by all operations. Contract-care (public server, ADR 0001).
