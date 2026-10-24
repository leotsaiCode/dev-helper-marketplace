# Documentation consistency report

Documents: 3; errors: 2; review candidates: 4; incomplete: false.

| Check | Certainty | Location | Observation | Related locations |
| --- | --- | --- | --- | --- |
| duplicate.paragraph | inference | AGENTS.md:5 | Normalized prose paragraph repeats. Decide whether to consolidate or retain intentional repetition. | README.md:8 |
| stale.candidate | inference | README.md:4 | Maintenance/deprecation marker found; it may be intentional. Verify current behavior and ownership. |  |
| rule.conflict_candidate | inference | README.md:6 | Opposite normative wording for the same normalized action. Check scope, exceptions and instruction precedence. | AGENTS.md:3 |
| stale.candidate | inference | docs/setup.md:3 | Maintenance/deprecation marker found; it may be intentional. Verify current behavior and ownership. |  |
| link.missing | deterministic | docs/setup.md:7 | Relative link has no local filesystem target (source-path check only). | docs/missing.md:- |
| nav.missing | deterministic | mkdocs.yml:- | No local source file at nav target. Confirm relative external URLs or generated pages before changing nav. | docs/absent.md:- |

## Coverage

- Conservative Markdown subset; no HTML, nested-parenthesis destinations, anchors, external URLs or rendered routes checked.
- No code/version/git-age verification; semantic results are review candidates only.
- Hidden, sensitive, dependency/build directories and directory symlinks excluded by policy.
- No MkDocs plugins, hooks, inheritance, environment expansion, exclude_docs or generated routes evaluated.

## Synchronization review scope

Direct relationships and literal mentions only; this is not a complete dependency graph.

- Changed: docs/setup.md
  - README.md: incoming link, literal path mention (candidate), outgoing link
  - mkdocs.yml: incoming nav
- Changed: src/client.py
  - docs/setup.md: literal path mention (candidate)
