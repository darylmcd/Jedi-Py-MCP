# cand-security-autofix — Security-finding autofix codemod (SEC022 first)

**row:** `cand-security-autofix` · **pri:** `Medium` · **size:** `S`

## Anchors

- `src/python_refactor_mcp/tools/metrics/security.py` (`_DANGEROUS_ATTR_CALLS` — `("yaml","load") → SEC022`; SEC020/SEC021 deserialization codes)
- `src/python_refactor_mcp/models.py` (`SecurityFinding` / `SecurityScanResult`)
- `src/python_refactor_mcp/util/cst_apply.py` (targeted codemod)
- change-stack tools (`begin/commit/rollback_change_stack`)

## Acceptance

- [ ] SEC022 `yaml.load(...)` → `yaml.safe_load(...)` CST codemod (inject `SafeLoader` where no `Loader=` kwarg is present); preview-by-default + change-stack rollback.
- [ ] Conservative skip + operator surface when an explicit non-default `Loader=` is already present (may be deliberate).
- [ ] SEC020/SEC021 deserialization codes are flag-only (no rewrite — no safe drop-in replacement); documented as such.
- [ ] Unit tests cover the bare `yaml.load(x)` rewrite and the explicit-Loader skip path.

## Evidence

- `security.py` already *detects* these patterns but emits findings only — there is no fixer anywhere in the tree. Verified non-overlap with `apply_lint_fixes` (Ruff `UP` covers language modernization, not SEC* injection/deserialization patterns).

## Context

- Source brainstorm: BRAIN-011. Scope first slice to SEC022 only; treat the deserialization codes as a flag-only follow-up. Could later dispatch through `cand-structural-replace` as the general engine, but slice 1 is a direct codemod.
