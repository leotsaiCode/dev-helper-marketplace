# Check semantics and report contract

## Evidence classes

`deterministic` records a filesystem observation within the scanner's supported
syntax and safety boundary. `inference` records a review candidate; it never
establishes semantic inconsistency or stale behavior. A normalized exact repeat
is observable, but whether repetition is a defect is inferred, so the finding
remains an inference. All candidates require human or agent verification.

| Rule | Certainty | Severity | Next verification step |
| --- | --- | --- | --- |
| `link.missing` | deterministic | error | Check source spelling, renderer and whether a generator owns the target |
| `link.unsafe` | deterministic | warning | Review boundary or symlink intentionally; target is not followed |
| `nav.missing` | deterministic for Markdown-source paths without explicit plugins/hooks; inference otherwise | error or warning respectively | Confirm this is intended as a source file, not a relative external URL or generated page |
| `nav.unsafe` | deterministic | warning | Review path boundary without following the target |
| `duplicate.paragraph` | inference | warning | Compare ownership and intentional repetition before consolidating |
| `rule.conflict_candidate` | inference | warning | Establish shared scope, precedence and exceptions |
| `stale.candidate` | inference | warning | Check implementation/version and whether deprecation or TODO is intentional |

The deterministic part of `nav.missing` means the local source is absent.
MkDocs can treat missing nav paths as external URLs. Even an error severity
here is a source-reference policy, not a guarantee that MkDocs build fails.
`line: null` for nav means the YAML parser did not preserve a reliable source
location. The report names the config and related target rather than inventing
a line number. Dynamic pages also affect Markdown links: `link.missing` is only
a filesystem assertion, not a rendered-site assertion.

## Coverage

Markdown syntax: inline links/images (including angle-bracket destinations,
optional quoted titles), full/collapsed/shortcut reference links, percent-encoded
paths, fragments and queries stripped before path lookup. Link targets are
resolved relative to the source file. Fragment-only links and URLs with a scheme,
network location or leading slash are skipped. Link targets are checked by type
and existence only; their content is not loaded merely because they are linked.
Directories count as existing filesystem targets, not proven rendered pages.

For links, code fences, indented code, inline code, frontmatter and HTML comments
are masked. Semantic paragraph/rule matching retains inline commands so different
tools or versions are not reduced to an identical action; marker checks mask them.
This is a conservative subset parser, not CommonMark: escaped punctuation,
nested labels/destinations, HTML links, multiline link definitions and renderer
extensions may be missed or misinterpreted. Anchor slug rules vary by renderer,
so fragments are not validated.

MkDocs: standard YAML lists/mappings, flow style, quotes, nested nav and
config-relative `docs_dir`. Root `mkdocs.yml` and `mkdocs.yaml` are detected;
explicit `--mkdocs-config` replaces auto-detection. A config without nav is
valid because MkDocs generates one, and nav need not list every document.
Both root `docs/` and supported custom docs trees are scanned. Unsupported YAML,
inheritance, unavailable parser, inaccessible config or invalid docs_dir yields
`coverage.skipped` and exit 2. Exclusion patterns and plugins are not evaluated;
the report always discloses this limitation. A missing config is only an error
when explicitly requested; no MkDocs configuration is a normal repository.

Semantic matching: casefolded whitespace-normalized exact paragraphs of at
least 40 characters, exact actions with opposite supported normative prefixes,
and explicit maintenance/deprecation markers. Different phrasing, synonyms,
command/package versions and implicit code/document drift require agent review.
Dates and filesystem modification times are never evidence of stale behavior.

## Schema 1.0

Top-level fields:

- `summary`: scanned document count, finding count, deterministic errors,
  inference candidates, and `incomplete` boolean.
- `coverage`: scanned document paths, selected configuration paths, skipped
  inputs with fixed reasons, and known limitations.
- `findings`: `rule`, `certainty`, `severity`, `path`, 1-based `line` or null,
  content-free `message`, and `related` path/line locations.
- `relationships`: `source`, `target`, source `line` or null, `kind` of link,
  nav, duplicate or rule. This inventory can include missing targets.
- `sync_scope`: each requested `changed` path with review paths and reasons.

Paths use repository-relative POSIX notation. Findings are sorted by source,
line and rule. No timestamps or absolute root paths are emitted. `--changed`
accepts deleted paths and source paths without reading them. Sync scope covers
direct inbound/outbound document relationships and exact path mentions;
transitive or conceptual dependencies are outside the MVP. An empty review list
means no supported relationship was found, not that no synchronization is needed.

The scanner does not export excerpts. To resolve a candidate, an agent should
report the narrow supporting evidence, applicable scope, and either a confirmed
issue or the evidence still missing. Do not promote candidates automatically.
