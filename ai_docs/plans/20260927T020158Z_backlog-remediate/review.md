# Plan review — 20260927T020158Z_backlog-remediate (cycle 0)

- Plan dir: `C:/Code-Repo/Jedi-Py-MCP/.worktrees/plan-20260927T020158Z_backlog-remediate/ai_docs/plans/20260927T020158Z_backlog-remediate`
- Stanza source: legacy-inline `plan.md` (`plan/` absent, ENOENT). Whole plan.md is 4991 bytes, under the 5120-byte bound.
- Rules: `C:/Users/daryl/.claude/prompts/backlog-remediate-rules.md` sha256 `47cbf122...598f29` (read directly; no slice supplied)
- Outcome: **passed-with-warnings** — block 0 · warn 1 · info 5
- Anchor verification: **performed**

## Summary

bl-0022 (6 production / 4 test files) is one coherent change inside a single subsystem, the tool-argument surface: the registration hook, the step model, and the path-validation consumer. The SDK mechanism holds against `.venv` mcp 2.1.1:

- `ArgModelBase` (`func_metadata.py:96-112`) sets no `extra`.
- `create_model(__base__=ArgModelBase)` is at `:358`.
- `MCPServer(tools=...)` is a public constructor param (`server.py:166,196`, into `ToolManager(tools=)`).
- `FuncMetadata.arg_model` and `Tool.parameters` are plain, non-frozen pydantic fields.
- `validate_arguments` reads `arg_model` live.

A live probe confirmed it. I subclassed `find_references`'s arg model with `extra="forbid"`, reassigned it and passed the tool through `MCPServer(tools=[t])`. `list_tools` then showed `additionalProperties:false`, and `bogus=1` was rejected with "Extra inputs are not permitted", naming `bogus`.

The `defect-forced-companion` citation for `tool_runtime.py` holds:

- `:82-83` and `:197` skip steps that are not dicts.
- Typed steps would therefore bypass the `_validate_params` path normalization at `:222-228` and the identifier checks at `:329`.

The breaking-change posture matches the addenda: a `changed-breaking-bl-0022.md` fragment, a `Changed — BREAKING` heading taken from `changelogHeadings`, and a PR-body callout.

There is one warn. The planned contract test asserts that every object schema, `$defs` included, has `additionalProperties:false`. The Approach forbids extras only on `SignatureOperation` and the new step models. But the live schemas also carry `Position`, `SymbolAnchor`, `Range` and `TextEdit` in `$defs`. Those are shared models that also parse raw Pyright LSP dicts.

## Findings

| Initiative | Severity | Rule | Evidence |
|---|---|---|---|
| bl-0022 | warn | 3 | The Approach contradicts its own contract test. A live probe (both profiles, 108 tools) found four `$defs` with no `additionalProperties`: `Position` (selection_range, diff_preview), `SymbolAnchor` (test_impact_select), and `Range` and `TextEdit` (diff_preview). The Approach forbids extras only on `SignatureOperation` and the step models, yet the test asserts every `$defs` object is `false`. Forbidding extras on the shared models (`models.py:10,17,23,38`) would also make `Range.model_validate(<raw LSP range>)` at `tools/refactoring/helpers.py:68,90` reject any extra LSP key. The strategy needs a decision: separate strict input models, or forbid on the shared models plus a lenient LSP parse. The decision must go into Risks. File count is unchanged (`models.py` is already in scope). |
| bl-0022 | info | 3 | Coherence holds: one subsystem. The `defect-forced-companion` citation resolves (`tool_runtime.py:82-83,197,222-228,329`) and names a concrete failure: typed steps silently skip workspace, absolute-path and identifier validation. `server.py` is forced by the `register_tools` removal (its sole production caller is `server.py:464`). Risks discloses the (a)/(b) split seam, and both halves serve the row's two Acceptance bullets. The SDK claims were verified against `.venv/Lib/site-packages/mcp` 2.1.1. |
| bl-0022 | info | 3 | The `refactor_transaction` docstring (`tool_registry.py:1527`) documents the INPUT-error contract ("malformed step, unsupported tool name ... RAISE"). After this change those cases fail in the SDK's `Tool.run` (`tools/base.py:148-152`), before `tool_error_boundary` runs. They come back as `ToolError("Error executing tool refactor_transaction: <ValidationError>")` with no `[INVALID_INPUT]` translation. The Approach does not update the docstring or the error-code expectation. |
| bl-0022 | info | 3 | The discriminated union "mirroring `rope_backend.py:82 TRANSACTION_TOOLS`" adds a second hand-maintained list of transaction tools. Derive one from the other, or assert they are equal in a test, so the union cannot drift from `TRANSACTION_TOOLS` / `_build_step_changes` (`rope_backend.py:1556-1595`). |
| bl-0022 | info | C2 | The stored and rebuilt edge sets agree (both empty). The stored cache `degrees:{}` / `zeroDegreeInitiatives:[]` omits order 1; the rebuild gives `{"1":0}` / `[1]`. This is an incomplete cache, not an edge disagreement. |
| bl-0022 | info | anchor | All cited anchors resolve at eb93918: `uv.lock:445`, `func_metadata.py:96-112,358`, `tool_registry.py:1910-1942`, `server.py:454-468`, `tool_params.py:155`, `models.py:352`, `rope_backend.py:82`, `tool_runtime.py:75-93,194-200,222-228,329`, `test_error_boundary.py:116,228,308,607`, `test_server.py:251`. The `ToolRecord` counts in the fanout note drift slightly (104 in `tool_registry.py` vs 102 claimed; 13 in `server.py` vs 14 claimed). This does not change any conclusion. |

## Per-rule walk (bl-0022)

| Rule | Result |
|---|---|
| stale-row | `bl-0022` is present (`ai_docs/backlog.md:67`). Its row dependency `bl-0021` is closed: absent from the index, and `changelog.d/changed-breaking-bl-0021.md` exists. |
| 1 | `rowsClosedCount` = 1, so N/A. |
| 3 | 6 files, over the 4-file target. The cited forcing shape holds (info). The Approach/test inconsistency is a warn (above). |
| 3b | `edit-only`. There are 4 `register_tools` call sites (1 production, 3 test), so this is not a solution-wide symbolic refactor. No finding. |
| 4 | 4 test files that all prove one shape: unknown-key rejection at the top level and in steps. No finding. |
| 5 | 60000 <= the 80000 marker. That is the top of the 3–4-file band, which is plausible for this 6-file change. No finding. |
| 5b | `fanoutEstimate` 6 is not above 6+2. `fanoutOversize` is false. A shape-B probe was performed. No finding. |
| deps | One node with `dependsOn: []`. No cycle and no unknown ids. |
| C2 / hotspot | Single initiative, so there are no consecutive pairs. It touches 3 addenda hotspots, but adjacency is N/A. |

## Conflict graph (reviewer-computed)

```json
{"edges": [], "degrees": {"1": 0}, "zeroDegreeInitiatives": [1]}
```

conflictGraphSeenOK: true. The edge sets match; the stored degree cache is incomplete (info).

## Hotspots

| Initiative | Hotspot files touched | Adjacent hotspot peer |
|---|---|---|
| bl-0022 (order 1) | `src/python_refactor_mcp/server.py`, `src/python_refactor_mcp/tool_registry.py`, `src/python_refactor_mcp/tool_runtime.py` | none (single initiative) |

## Stale rows

| Initiative | Row | Present in backlog |
|---|---|---|
| bl-0022 | bl-0022 | yes |

## Recommended next step

The plan can proceed (passed-with-warnings). Before execution, amend the Approach and Risks with `stanza-amend` to settle nested-`$defs` strictness. Pick one:

- **(a)** Forbid extras on `Position`, `Range` and `TextEdit`. First confirm that LSP parsing at `helpers.py:68,90` tolerates this, or switch that path to a lenient parse.
- **(b)** Narrow the contract-test assertion to the tool-owned input models.

In the same amendment, add the `tool_registry.py:1527` docstring update to the Approach.
