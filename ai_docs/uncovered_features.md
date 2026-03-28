# Uncovered Library Features

Features available in Pyright, Rope, and Jedi that are **not yet exposed** by this MCP server, prioritized by usefulness.

> Generated 2026-03-27. Cross-referenced against the 45 tools currently exposed.

---

## Priority 1 — High Impact

| # | Feature | Source | Description |
|---|---------|--------|-------------|
| 1 | **Inline Method** | Rope (`InlineMethod`) | Inline a function/method body into all call sites and remove the original. Current `inline_variable` only handles variables. |
| 2 | **Inline Parameter** | Rope (`InlineParameter`) | Remove a parameter from a function signature by inlining its default value into the body. |
| 3 | **Move Method** | Rope (`MoveMethod`) | Move a method from one class to another, creating a delegate in the original. Current `move_symbol` only handles globals. |
| 4 | **Move Module** | Rope (`MoveModule`) | Move/rename an entire module or package, updating all imports project-wide. |
| 5 | **Get Syntax Errors** | Jedi (`Script.get_syntax_errors`) | Detect syntax errors in a file without running Python. Complements Pyright diagnostics with Jedi's parser. |
| 6 | **Expand Star Imports** | Rope (`ImportOrganizer.expand_star_imports`) | Replace `from x import *` with explicit named imports. Critical for code quality. |
| 7 | **Create Type Stubs** | Pyright (`pyright.createtypestub`) | Generate `.pyi` type stub files for untyped third-party packages. |
| 8 | **Code Generation** | Rope (`rope.contrib.generate`) | Generate missing classes, functions, variables, modules, and packages from usage sites. |
| 9 | **Type Inference (deep)** | Jedi (`Script.infer`) | Follow imports and statements to resolve the final type of a symbol. Deeper than `get_type_info`. |
| 10 | **Get Type Hint String** | Jedi (`Name.get_type_hint`) | Return a type annotation string like `Iterable[int]` for a symbol — useful for adding type hints. |

## Priority 2 — Medium Impact

| # | Feature | Source | Description |
|---|---------|--------|-------------|
| 11 | **Argument Normalizer** | Rope (`ArgumentNormalizer`) | Normalize call-site arguments to match definition order. Useful for consistent code style. |
| 12 | **Argument Default Inliner** | Rope (`ArgumentDefaultInliner`) | Inline a parameter's default value into all call sites that omit it, then remove the default. |
| 13 | **Relatives to Absolutes** | Rope (`ImportOrganizer.relatives_to_absolutes`) | Convert all relative imports to absolute imports. |
| 14 | **Froms to Imports** | Rope (`ImportOrganizer.froms_to_imports`) | Convert `from module import name` to `import module` style. |
| 15 | **Handle Long Imports** | Rope (`ImportOrganizer.handle_long_imports`) | Break long import lines per project preferences. |
| 16 | **Get Context (enclosing scope)** | Jedi (`Script.get_context`) | Return the enclosing function/class/module at a position. Useful for scope-aware operations. |
| 17 | **Get All Names** | Jedi (`Script.get_names`) | List all defined names in a file (optionally all scopes). Broader than `get_symbol_outline`. |
| 18 | **Find Errors (static)** | Rope (`rope.contrib.finderrors.find_errors`) | Rope's own static analysis for bad name/attribute accesses. Complements Pyright diagnostics. |
| 19 | **Fix Module Names** | Rope (`rope.contrib.fixmodnames.FixModuleNames`) | Batch-rename modules to conform to naming conventions (e.g., PEP 8 lowercase). |
| 20 | **AutoImport Cache** | Rope (`rope.contrib.autoimport.AutoImport`) | SQLite-backed cache of all global names for fast auto-import suggestions across the project. |

## Priority 3 — Specialized / Niche

| # | Feature | Source | Description |
|---|---------|--------|-------------|
| 21 | **Undo/Redo History** | Rope (`rope.base.history.History`) | Track and undo/redo refactoring changes with dependency-aware rollback. |
| 22 | **Change Stack** | Rope (`rope.contrib.changestack.ChangeStack`) | Chain multiple refactorings into one atomic change set. |
| 23 | **Multi-Project Refactoring** | Rope (`MultiProjectRefactoring`) | Apply refactorings across multiple Rope projects simultaneously. |
| 24 | **Fuzzy Completion** | Jedi (`Script.complete(fuzzy=True)`) | Fuzzy matching for completions (e.g., "ooa" matches "foobar"). |
| 25 | **Project-wide Search** | Jedi (`Project.search` / `Project.complete_search`) | Semantic search across entire project using Jedi's analysis (complements Pyright symbol search). |
| 26 | **Keyword/Operator Help** | Jedi (`Script.help`) | Documentation for Python keywords and operators, not just names. |
| 27 | **Simulate Execution** | Jedi (`Name.execute`) | Simulate calling a callable and return the result types. |
| 28 | **Sub-definitions** | Jedi (`Name.defined_names`) | List sub-definitions of a name (e.g., methods of a class from a reference). |
| 29 | **Environment Management** | Jedi (`create_environment`, `find_virtualenvs`, etc.) | Discover and manage Python environments/virtualenvs. |
| 30 | **Restart Server** | Pyright (`pyright.restartserver`) | Discard cached type info and restart Pyright analysis. |

## Already Covered (for reference)

The following capabilities from these libraries are already exposed as MCP tools:

**Pyright (via basedpyright):** hover, completions, completion resolve, diagnostics (file + workspace), goto definition, declaration, type definition, references, document symbols, workspace symbols, document highlight, rename (prepare + execute), code actions, organize imports, signature help, call hierarchy, semantic tokens, inlay hints, folding ranges, selection range, find implementations.

**Rope:** Rename, extract method, extract variable, inline variable, move global, change signature (add/remove/reorder params), restructure, encapsulate field, introduce factory, introduce parameter, local to field, method object, module to package, use function.

**Jedi (as fallback or primary):** references, type info, hover info, documentation, call signatures, goto definition, symbol search, import suggestions.

**Custom:** structural search (libcst), dead code detection, diff preview, find constructors.
