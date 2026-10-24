# docs-consistency-guard

A documentation consistency checker built around a standard [Agent Skills](https://agentskills.io/specification) `SKILL.md`.
The CLI provides reproducible local checks, and the AI coding agent handles evidence-based semantic review.
It only reads and never modifies documentation; possible staleness and rule conflicts are always kept as hints to confirm.

## Quick start

Requires Python 3.10+ on Linux or macOS. The examples below use [uv](https://docs.astral.sh/uv/);
the CLI core uses only the Python standard library. Scanning does not use the network, read environment variables, or run Git, project code, or MkDocs plugins.

Run from the root of the project you want to check:

```sh
uvx --from git+https://github.com/leotsaiCode/dev-helper-marketplace docs-consistency-guard --root . --format markdown
```

To check MkDocs YAML, add the only optional runtime dependency, PyYAML:

```sh
uvx --from git+https://github.com/leotsaiCode/dev-helper-marketplace --with pyyaml docs-consistency-guard --root . --format json
uvx --from git+https://github.com/leotsaiCode/dev-helper-marketplace --with pyyaml docs-consistency-guard --root . --format markdown --output docs-report.md
```

You can also install the CLI with `uv tool install git+https://github.com/leotsaiCode/dev-helper-marketplace --with pyyaml`. Without a MkDocs config you do not need PyYAML;
if a config exists but PyYAML is missing, the tool reports the check as incomplete with exit 2 instead of pretending it succeeded.
Installing dependencies may use the network; scanning itself does not. For `--output`, the parent directory must already exist, the target file must not exist, and the parent path must not contain symlinks.
On macOS, use `/private/tmp/...` instead of `/tmp/...`, which is usually a symlink.

```sh
uvx --from git+https://github.com/leotsaiCode/dev-helper-marketplace --with pyyaml docs-consistency-guard --root . \
  --mkdocs-config config/mkdocs.yml \
  --changed src/client.py --changed docs/setup.md --format json
```

`--changed relative/path` is repeatable and sets a direct synchronization review scope.

By default it recursively finds `README.md`, `AGENTS.md`, `CLAUDE.md`, and `CONTRIBUTING.md` at every level,
plus Markdown in the root `docs/` and in any `docs_dir` that can be resolved safely.
Supported extensions are `.md`, `.markdown`, `.mdown`, `.mkdn`, and `.mkd`.
MkDocs lookup only checks the root `mkdocs.yml` and `mkdocs.yaml` by default; specify other configs with `--mkdocs-config`.
Other ordinary Markdown (for example a root `SKILL.md` or `README.en.md`) is outside the default scan scope.

| Check | What the CLI can observe with certainty | What needs review |
| --- | --- | --- |
| Relative Markdown links | Whether local files/directories in supported syntax exist | Rendered routes, plugins, HTML, and anchors are not checked |
| MkDocs nav | Whether local source files relative to `docs_dir` exist | Generated pages, whether relative external URLs are valid |
| Repeated text | Locations of paragraphs that are identical after normalization | Whether to merge, near-duplicates |
| Conflicting rules | Pairs of opposite normative statements about the same action | Whether the scope is the same, exceptions, instruction precedence |
| Possible staleness | Markers such as TODO, deprecated, or needs-update | Whether it is actually stale; never judged by file age |
| Sync scope | Link relationships, repeat/rule associations, literal mentions of changed paths | Implicit dependencies and full impact analysis |

MkDocs accepts relative external navigation URLs, so a missing source file is reported separately from a broken built site.

The English rule MVP supports line-initial `must`, `must not`, `always`, and `never` (optionally after a list marker and `You`);
for Chinese it supports `必須`, `務必`, `禁止`, `不得`, and `不要`. Only identical action text following the keyword is compared.
The CLI does not use an LLM and does not claim to detect arbitrary natural-language contradictions, near-duplicates, or version drift.

### Exit codes and reports

| Code | Meaning |
| --- | --- |
| 0 | Scan of the supported scope completed with no deterministic errors; warnings or semantic candidates may still exist |
| 1 | Deterministic errors, such as a missing local source |
| 2 | Bad arguments, root, or output, or a required input/config could not be fully checked because of limits; takes precedence over 1 |

Candidates alone do not fail the gate.

JSON `schema_version: "1.0"` contains `summary`, `coverage`, `findings`,
`relationships`, and `sync_scope`. `certainty` is either `deterministic` or `inference`;
`severity` is separate from certainty. See [checks](../../plugins/docs-consistency-guard/skills/docs-consistency-guard/references/checks.md) for examples, fields, and limits.
The Markdown report suits review; JSON suits CI. Output does not include document text, URL queries, or secret values,
but it does include paths, line numbers, and relationships between files, so review it before sharing.

### Use across agents

Choose Skills CLI or the Claude/Codex plugin through the collection's [installation guide](../../README.md).
For a manual install, take only `plugins/docs-consistency-guard/skills/docs-consistency-guard/` and keep the folder name `docs-consistency-guard`.
The skill's own scripts, references, and LICENSE are installed with it; the collection's tests, examples, and pyproject.toml are not needed.
[SKILL.md](../../plugins/docs-consistency-guard/skills/docs-consistency-guard/SKILL.md) uses standard frontmatter, relative resource links, and explicit evidence boundaries.
When an agent is asked to "check whether the docs are consistent", it runs the CLI first, then reviews the results according to the [references](../../plugins/docs-consistency-guard/skills/docs-consistency-guard/references/checks.md).

### Security and limits

Hidden directories, dependency/build directories, and paths whose names carry sensitive markers are excluded by default; arbitrary source code and `.env` are never read.
Directory descriptors and `O_NOFOLLOW` reject symlinks within the scan, paths outside the root are rejected,
and files are limited to regular UTF-8 files with caps on size, count, and traversed entries. Calling `resolve` alone is not treated as a security boundary.
YAML uses SafeLoader and rejects tags, anchors, aliases, duplicate keys, and `INHERIT`;
`!ENV` is not expanded and hooks are not run. These valid but unsupported MkDocs features are listed as coverage gaps.
`exclude_docs`, `not_in_nav`, custom Markdown extensions, and plugin-generated output are not parsed.
See [security](../../plugins/docs-consistency-guard/skills/docs-consistency-guard/references/security.md) for details. Name-based exclusion is not a secret detector; allowed documents can still contain sensitive text.

### Tests and examples

```sh
uv run --locked --no-editable --group test --extra mkdocs pytest tests/plugins/docs-consistency-guard
uv run --no-editable --extra mkdocs docs-consistency-guard --root examples/docs-consistency-guard/demo --format markdown
```

The second command is expected to exit 1 because the [demo](../../examples/docs-consistency-guard/demo/README.md) deliberately contains errors;
compare against the [sample report](../../examples/docs-consistency-guard/report.md) and [JSON report](../../examples/docs-consistency-guard/report.json).
CI runs the tests on Linux/macOS with Python 3.10/3.13, and also verifies the core path without PyYAML and the packaged CLI.
Single-plugin tests do not include the cross-plugin install check; for full validation, run
`uv run --locked --no-editable --group test --extra mkdocs pytest` from the root.

Contributions follow [CONTRIBUTING.md](../../CONTRIBUTING.md).
MIT licensed. Official assumptions and verification sources are recorded in
[references/sources.md](../../plugins/docs-consistency-guard/skills/docs-consistency-guard/references/sources.md).
