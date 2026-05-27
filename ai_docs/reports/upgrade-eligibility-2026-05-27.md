# Upgrade Eligibility Report — Jedi-Py-MCP — 2026-05-27

**Pass:** 1 (analysis only — no manifest edits made)
**Operator:** darylmcd
**Generator:** `prompts/upgrade-eligibility-matrix-prompt.md`

## Summary

- Repos analyzed: 1 (Jedi-Py-MCP)
- Manifests scanned: `pyproject.toml`, `requirements.txt`, `pyrightconfig.json`, `.github/workflows/ci.yml`, `uv.lock`
- Total dependencies inventoried: 12 (6 runtime + 4 dev + 1 build-backend + 1 packaging)
- CVE-mandatory bumps: 0 (`pip-audit` against `requirements.txt`: "No known vulnerabilities found")
- Reproducibility-risk pins: **all 12** (every pin is `>=` only; uv.lock is the authoritative snapshot)
- Major-review candidates: 1 (`mypy` 1.19 → 2.x)
- EOL signals: 0 (Python 3.14 is current GA; all packages on supported lines)
- Drift hotspots (cross-repo): 1 (`pyright` — Jedi-Py-MCP `>=1.1.380` lock 1.1.408 vs CLI-Inventory-Tool `==1.1.408` vs Firewall-Policy-Review `>=1.1`)
- Documentation/manifest drift findings: 2 (see "Open Questions" — `requirements.txt` duplicates `pyproject.toml`; `hatchling` mis-classified in `requirements.txt`)

## Runtime / SDK floor

| Item | Value | Source |
|---|---|---|
| Python `requires-python` | `>=3.14` | `pyproject.toml:10` |
| Pyright `pythonVersion` | `3.14` | `pyrightconfig.json:8` |
| Mypy `python_version` | `3.14` | `pyproject.toml:63` |
| Ruff `target-version` | `py314` | `pyproject.toml:37` |
| CI matrix | `python-version: "3.14"` (Windows only) | `.github/workflows/ci.yml:30` |
| Dockerfile / docker-compose | none present | — |

Floor is internally consistent — no SDK-floor row needed.

## Eligibility Matrix — Jedi-Py-MCP

Resolved version comes from `uv.lock` (authoritative). "Latest stable" verified via `pip index versions <pkg>` on 2026-05-27.

| Package | Manifest pin | uv.lock resolved | Latest stable | Gap | Eligibility | Blockers | CVE | Notes |
|---|---|---|---|---|---|---|---|---|
| mcp | `>=1.20` | 1.26.0 | 1.27.1 | minor (1.26→1.27) | MINOR-SAFE | none | none | Floor pin is 6 minors behind lock. Recommend bumping pin to `>=1.26` to truth-up the lock; bump to 1.27.1 in same PR. Pre-1.0 → 1.x: API stable since 1.0. |
| pydantic | `>=2.0` | 2.12.5 | 2.13.4 | minor | MINOR-SAFE | none | none | Pydantic 2.x is stable; 2.13 is feature-add. Repo uses pydantic models extensively — re-run tests after bump. |
| jedi | `>=0.19` | 0.19.2 | 0.20.0 | minor (0.x bumps treated as minor) | MINOR-SAFE | none | none | 0.20 changelog: drops Python 3.7/3.8 support (irrelevant — repo is 3.14). Verify `JediBackend` still works against the lock pin advance. |
| rope | `>=1.13` | 1.14.0 | 1.14.0 | none | PATCH-EASY | none | none | Already at latest. Bump pin to `>=1.14` to truth-up. |
| pyright | `>=1.1.380` | 1.1.408 | 1.1.409 | patch | PATCH-EASY | none | none | **DRIFT vs CLI-Inventory-Tool (`==1.1.408`).** Recommend aligning fleet to 1.1.409 (or pin Jedi-Py-MCP to `==1.1.409` to match the other repo's exact-pin style). |
| libcst | `>=1.1` | 1.8.6 | 1.8.6 | none | PATCH-EASY | none | none | Already at latest. Floor pin is 7 minors behind lock. Bump pin to `>=1.8`. Repo recently added `util/cst_apply.py` (PR #35) which depends on libcst — exposure to libcst's API surface has grown; verify lock-aligned floor doesn't regress. |
| pytest | `>=8.0` | 9.0.2 | 9.0.3 | patch | PATCH-EASY | none | none | **Floor crosses major (8→9).** Lock already on 9.x but pin says 8. Bump pin to `>=9.0`. |
| pytest-asyncio | `>=0.24` | 1.3.0 | 1.4.0 | minor | MINOR-SAFE | none | none | **Floor crosses major (0.x→1.x).** Lock already on 1.x but pin says 0.24. Bump pin to `>=1.3` and update lock to 1.4.0. |
| ruff | `>=0.8` | 0.15.8 | 0.15.14 | patch | PATCH-EASY | none | none | Ruff is rapid-release; floor pin (0.8) is ancient relative to lock (0.15). Bump pin to `>=0.15`. |
| mypy | `>=1.13` | 1.19.1 | **2.1.0** | **major** | **MAJOR-REVIEW** | strict mode | none | mypy 2.0 dropped several legacy flags + tightened inference. Repo runs `strict = true` in `[tool.mypy]` — high probability of new errors. Read mypy 2.0 release notes before any bump. Defer; lock to 1.x for now. |
| hatchling | `>=1.25` (build-system) | n/a (build-time only) | 1.29.0 | minor | PATCH-EASY | none | none | Build backend in `[build-system].requires`. Bump pin to `>=1.29`. **Also mis-classified in `requirements.txt`** — see Open Questions. |
| pyinstaller | `>=6.0` | 6.19.0 | 6.20.0 | patch | PATCH-EASY | none | none | Bump pin to `>=6.19`. Used by `scripts/build-binary.ps1` to produce the standalone exe. |

### Cross-cutting findings (not per-row)

- **REPRODUCIBILITY-RISK (acknowledged in Appendix A.2):** every pin in `pyproject.toml` is `>=` only. Mitigation is `uv.lock` (present, 112KB, committed at `fdc9b77`). Continue requiring `uv lock` regeneration on every dep change. *No action needed beyond bumping floor pins to match lock.*

## Cross-Repo Drift

| Package | Jedi-Py-MCP | CLI-Inventory-Tool | Firewall-Policy-Review | Drift Reason | Proposed Single Target |
|---|---|---|---|---|---|
| pyright | `>=1.1.380` (lock 1.1.408) | `==1.1.408` exact (also `package.json` 1.1.408 exact) | `>=1.1` | None documented. CLI-Inventory-Tool pins exact for CI determinism; the others rely on `>=`+lock. | `1.1.409` (latest). Strategy: Jedi-Py-MCP bumps pin to `>=1.1.409`; CLI-Inventory-Tool bumps exact pin to `1.1.409`; Firewall-Policy-Review tightens `>=1.1` to `>=1.1.409`. |
| Python floor | `>=3.14` | `3.14` (mypy/ruff config) | `>=3.11` | Operator-flagged in Appendix C #4. Firewall-Policy-Review/panos_audit lags 3 minors. | Operator decision — see Appendix C #4. Out of scope for this single-repo run. |

**No other cross-repo drift involving Jedi-Py-MCP packages** — `mcp`, `pydantic`, `jedi`, `rope`, `libcst`, `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `hatchling`, `pyinstaller` are not pinned in any sibling repo's snapshot.

## Recommended Upgrade Patch — Jedi-Py-MCP

### Batch 1: floor-truthing patch-bumps (PATCH-EASY)

- **Batch ID:** `jedi-py-mcp-batch-1-floor-truthing`
- **Scope:** `pyproject.toml` only (no code changes). Bump every floor pin so the manifest minimum ≤ uv.lock resolved version, eliminating the silent drift between manifest and lock. Same-PR lock refresh via `uv lock` (no version bumps requested in lock).
  | Package | Old min | New min |
  |---|---|---|
  | rope | `>=1.13` | `>=1.14` |
  | pyright | `>=1.1.380` | `>=1.1.408` |
  | libcst | `>=1.1` | `>=1.8` |
  | pytest | `>=8.0` | `>=9.0` |
  | ruff | `>=0.8` | `>=0.15` |
  | hatchling | `>=1.25` | `>=1.29` |
  | pyinstaller | `>=6.0` | `>=6.19` |
- **Pre-requisites:** none.
- **Validation:** `uv lock --check` (no lock drift), `ruff check .`, `pyright .`, `mypy .`, `pytest tests/unit/ -v`, `scripts/test-integration.ps1`.
- **Rollback:** single revert commit (manifest-only change; lock is idempotent at the same resolved versions).
- **PR title:** `chore(deps): truth-up pyproject floor pins to match uv.lock`
- **PR body skeleton:**
  > Tightens 7 dependency floor pins in `pyproject.toml` so the declared minimum ≥ what `uv.lock` already resolves. No resolved version changes; no functional change. Eliminates the silent drift between manifest and lock that complicates fleet-wide audits.

### Batch 2: minor bumps with lock refresh (MINOR-SAFE)

- **Batch ID:** `jedi-py-mcp-batch-2-minor-refresh`
- **Scope:** Advance the lock on 5 packages where a minor exists; tighten floor pins to the new lock.
  | Package | Lock now | Lock target | New pin |
  |---|---|---|---|
  | mcp | 1.26.0 | 1.27.1 | `>=1.27` |
  | pydantic | 2.12.5 | 2.13.4 | `>=2.13` |
  | jedi | 0.19.2 | 0.20.0 | `>=0.20` |
  | pytest-asyncio | 1.3.0 | 1.4.0 | `>=1.4` |
  | pyright | 1.1.408 | 1.1.409 | `>=1.1.409` |
- **Pre-requisites:** Batch 1 merged green.
- **Validation:** `uv lock --upgrade-package mcp pydantic jedi pytest-asyncio pyright`, full CI matrix, **manual smoke: launch the MCP server and exercise `find_references` + `rename_symbol` to verify jedi 0.20 + mcp 1.27 don't regress** (jedi 0.20 API surface change; mcp protocol additions in 1.27).
- **Rollback:** single revert commit; lock is recomputable from the prior `pyproject.toml`.
- **PR title:** `chore(deps): refresh mcp/pydantic/jedi/pytest-asyncio/pyright lock + floor pins`
- **PR body skeleton:**
  > Lock-and-pin refresh for 5 deps. mcp 1.26→1.27 (protocol additions, backward compatible). pydantic 2.12→2.13 (feature release). jedi 0.19.2→0.20.0 (drops legacy Python — repo is 3.14, unaffected). pytest-asyncio 1.3→1.4 (no breaking notes). pyright 1.1.408→1.1.409 (resolves cross-repo drift with CLI-Inventory-Tool).

### Batch 3: requirements.txt cleanup (REPRODUCIBILITY-RISK + drift)

- **Batch ID:** `jedi-py-mcp-batch-3-requirements-cleanup`
- **Scope:** Either (a) delete `requirements.txt` (uv.lock + pyproject.toml are authoritative), or (b) regenerate it from `uv lock --export` so it tracks the lock. **Operator decision required** — see Open Questions #1.
- **Pre-requisites:** Batches 1+2 merged.
- **Validation:** if (a): grep all docs + CI workflow for `requirements.txt` references; confirm none. If (b): `uv export --format requirements-txt > requirements.txt`; verify hatchling no longer appears (build-system only); add a header banner "auto-generated from uv.lock — do not edit by hand."
- **Rollback:** trivial — restore the file.
- **PR title:** `chore(deps): {drop|regenerate} requirements.txt — uv.lock is authoritative`
- **PR body skeleton:**
  > `requirements.txt` duplicates `pyproject.toml` (with subtle classification drift — `hatchling` belongs in `[build-system].requires`, not the runtime/dev list). The lockfile (`uv.lock`) is the actual source of truth. {Drops the file outright | Regenerates it from `uv lock --export` and marks it generated}.

### Batch 4: mypy 2.x major review (MAJOR-REVIEW — defer until release-notes review)

- **Batch ID:** `jedi-py-mcp-batch-4-mypy-2x`
- **Scope:** `pyproject.toml` — bump `mypy>=1.13` to `mypy>=2.0` and let lock advance to 2.1.0. Almost certainly requires source edits to silence/fix new strict-mode errors.
- **Pre-requisites:** Batches 1–3 merged. Operator approval to spend a session on the mypy 2.x migration (could surface 50+ new errors against a `strict = true` codebase).
- **Validation:** `mypy .` clean; CI green; no `# type: ignore` insertions to silence regressions (per Standing Engineering Directive #1 — fix root cause, don't band-aid).
- **Rollback:** revert if regressions exceed budget; mypy 1.19 remains supported.
- **PR title:** `chore(deps): upgrade mypy 1.19 → 2.x`
- **PR body skeleton:**
  > Major-version bump. mypy 2.0 dropped legacy flags and tightened inference. Repo runs `strict = true`, so expect new errors. This PR fixes them at the source level (no `# type: ignore` band-aids per Standing Engineering Directive #1).

## Replacement Recommendations (BLOCKED-EOL)

None. All packages are on actively-maintained lines.

## Open Questions for Operator

1. **`requirements.txt` disposition** — drop the file outright (uv.lock + pyproject.toml are authoritative), or regenerate from `uv export --format requirements-txt` so it tracks the lock? Status quo (hand-maintained duplication of pyproject.toml, plus `hatchling` mis-classified as a runtime/dev dep instead of a build-system requirement) is a low-grade drift risk. Recommend: **drop**, since CI installs via `pip install -e ".[dev,build]"` (`.github/workflows/ci.yml:39`) and never reads `requirements.txt`.

2. **Pyright fleet alignment style** — Jedi-Py-MCP uses `>=` pins backed by uv.lock; CLI-Inventory-Tool pins `==1.1.408` exact in both `requirements-dev.txt` and `package.json`. Single target version is easy (1.1.409) but the *pin style* differs by philosophy. Recommend: align on `>=1.1.409` for Jedi-Py-MCP (Batch 2), and CLI-Inventory-Tool bumps its exact pin separately. Don't conflate styles.

3. **mypy 2.x upgrade timing** — Batch 4 is deferred by default. Approve to proceed, or park behind some other deadline?

4. **Cross-repo Python-floor alignment (Appendix C #4)** — out of scope for this single-repo run, but flagged for fleet-aware planning: Firewall-Policy-Review/panos_audit lags at `>=3.11` while Jedi-Py-MCP and CLI-Inventory-Tool are at `>=3.14`. Schedule a separate sweep when ready.

5. **Approval to proceed to Pass 2** — if you approve any specific batch (e.g. "approved — apply batch 1"), I'll create `upgrade/jedi-py-mcp-batch-1-floor-truthing`, edit `pyproject.toml`, run the validation checklist, commit, and push without opening a PR per § 8.

## Methodology notes (provenance)

- Latest-stable versions verified via `pip index versions <pkg>` on 2026-05-27, one call per package, results cached for this run.
- CVE coverage verified via `pip-audit -r requirements.txt` — clean.
- Resolved versions read from `uv.lock` (verified present at HEAD, 112KB, last committed in fdc9b77's chain).
- No registry was unreachable; no manifest was malformed; no package was absent upstream.
- No edits made under this Pass 1 run — `git status` clean except for the new report file.
