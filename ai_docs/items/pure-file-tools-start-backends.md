# pure-file-tools-start-backends — Pure file/AST tools should not start backends

**row:** `pure-file-tools-start-backends` · **pri:** `Low` · **size:** `M`

## Anchors

- `src/python_refactor_mcp/tool_registry.py:1423`
- `src/python_refactor_mcp/tool_registry.py:1464`
- `src/python_refactor_mcp/tool_registry.py:1477`
- `src/python_refactor_mcp/tool_registry.py:1531`
- `src/python_refactor_mcp/tool_registry.py:1544`
- `src/python_refactor_mcp/tool_registry.py:1552`
- `src/python_refactor_mcp/tool_registry.py:1886`

## Acceptance

- [ ] Re-derive the list: every tool whose body does `_ = get_current_backends()` and never uses the result (about 20; examples `code_metrics`, `find_duplicated_code`, `get_type_coverage`, `interface_conformance`, `extract_protocol`, `get_module_public_api`, `security_scan`). Pin the list in a test.
- [ ] Each moves to the `WorkspaceUse.ROOT_ONLY` record mode and drops the discarded call; no Pyright/Jedi/rope starts for these tools.
- [ ] Real-registry test per mode: such a tool succeeds with zero live backends without starting any.

## Evidence

- Same mechanism as `diff-preview-root-only`: the boundary resolves backends for tools that only read files or parse the AST, spinning up language servers needlessly. Sketch list in `D:/Jedi-Py-MCP/.worktrees/bl-0056.report.md`.

## Context

- Follows `diff-preview-root-only` (the `ROOT_ONLY` scaffold) and `bl-0056` (path-less semantics; those tools' path-less behaviour must be decided with PR B's `root_path`).
