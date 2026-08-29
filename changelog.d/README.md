# Changelog fragments

Add exactly one nonblank bullet to one file per logical change.

| Filename prefix | Required bullet prefix | Release heading |
|---|---|---|
| `fixed-` | `- **Fixed:** ` | `Fixed` |
| `changed-breaking-` | `- **Changed — BREAKING:** ` | `Changed — BREAKING` |
| `changed-` | `- **Changed:** ` | `Changed` |
| `added-` | `- **Added:** ` | `Added` |
| `maintenance-` | `- **Maintenance:** ` | `Maintenance` |

Use `<category>-<lowercase-kebab-slug>.md`. `scripts/changelog_fragments.py`
validates filenames, category prefixes, and one-bullet content. Pull requests
that change source, tests, build/release tooling, workflows, or public docs must
change at least one valid fragment. Planning-only changes are exempt.

`scripts/bump_reinstall.py` validates all fragments, groups them in the table
order, writes the dated release under the empty `Unreleased` anchor, and deletes
only the consumed fragments. Pre-install release failures restore both the
changelog and fragments.
