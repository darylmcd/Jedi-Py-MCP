# changelog-fragment-release-workflow — Migrate Unreleased notes to validated fragments

**row:** `changelog-fragment-release-workflow` · **pri:** `Medium` · **size:** `M`

## Anchors

- `CHANGELOG.md` — populated Unreleased section and release-link anchors
- `changelog.d/README.md` — new fragment schema and release-consumption contract
- `scripts/bump_reinstall.py` — consume validated fragments during the existing release bump
- `.github/workflows/ci.yml` — require a valid changed fragment for change-bearing pull requests

## Acceptance

- [ ] Convert every current Unreleased bullet into one or more traceable fragments, leaving a single empty Unreleased structural anchor.
- [ ] Validate lowercase kebab-case filenames, the category enum, matching body prefixes, and exactly one nonblank bullet per fragment.
- [ ] Require a changed fragment for source, test, build, workflow, or public-documentation changes while exempting planning-only changes.
- [ ] Make `bump-reinstall` group fragments in canonical category order, assemble the dated release, and delete only the fragments it consumed.
- [ ] Add regression tests for malformed fragments, missing fragments, category ordering, atomic consumption, and release rollback.

## Evidence

- Jedi-Py-MCP currently writes all pending notes directly into a large `CHANGELOG.md` Unreleased section and has no `changelog.d` directory or validator.
- Roslyn-Backed-MCP's fragment workflow assumes an empty Unreleased section, so copying only its validator here would create two competing release-note authorities.
