# cand-rename-cst-alias — LibCST alias-aware rename across imports

**row:** `cand-rename-cst-alias` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tools/refactoring/rename.py` (current rope-based `rename_symbol`)
- `src/python_refactor_mcp/util/cst_apply.py` (alias-aware edit emission)
- `src/python_refactor_mcp/tools/analysis/references.py` (`find_references`)

## Acceptance

- [ ] A single-module `rename_symbol` variant (or flag) rewrites `import X as Y` / `from m import X as Y` consistently where rope/Jedi miss alias re-bindings.
- [ ] Alias-collision-with-existing-binding-in-target-scope handled (conservative abort or explicit conflict surface).
- [ ] Dry-run-first; change-stack rollback honored.
- [ ] Unit tests cover an alias-heavy module (`import X as Y` rebind + `from m import X as Y`).

## Evidence

- Rename is the highest-frequency refactor; rope/Jedi under-serve alias rebindings on alias-heavy codebases. The LibCST apply scaffold (#35) provides the needed rewrite path.

## Context

- Source brainstorm: BRAIN-001. Risk: conflict resolution when an alias collides with an existing binding — needs a rollback story tied to the change-stack tools.
