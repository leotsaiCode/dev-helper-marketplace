# Contributing

Each plugin lives in `plugins/<plugin-name>/`, with its Claude/Codex plugin manifests and a LICENSE.
Each skill lives in that plugin's `skills/<skill-name>/`, and the `name` in `SKILL.md` must match the folder name.
Put only the scripts, references, assets, and license the skill needs at runtime inside it.
A skill must run after a standalone install: use resource paths relative to its own directory and do not depend on the repo root.

Plugin tests go in `tests/plugins/<plugin-name>/test_*.py`; that plugin's fixtures stay in the same folder.
Marketplace settings and cross-plugin install tests go in `tests/marketplace/`.
Tests use pytest fixtures, plain asserts, and parametrized cases, with a separate temporary directory per case.
Examples go in `examples/<skill-name>/`,
human-facing guides go in `docs/skills/<skill-name>.md`, linked from the table in the root README.
Do not put a real `SKILL.md` in these development directories, where an installer could mistake it for a skill.

Register a new plugin in both the root `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`,
with the source pointing to `./plugins/<plugin-name>`. The root only provides marketplaces; do not put a plugin.json or SKILL.md there.
Each plugin's Claude/Codex manifests scan `./skills/` inside their own directory, so new skills do not need to be listed one by one.
Both manifests of a plugin must share the same name and version; different plugins can bump versions independently.
Keep skill names unique across the whole repo so Skills CLI name selection is unambiguous.
Do not reference another skill's runtime resources from the current skill, or a standalone install will be missing files.

Run from the repo root:

```sh
uv run --locked --no-editable --group test --extra mkdocs pytest
uv run --locked --no-editable --group test --extra mkdocs pytest tests/plugins/docs-consistency-guard
uv run --locked --no-editable --group test --extra mkdocs pytest -m integration -v
claude plugin validate .
claude plugin validate plugins/docs-consistency-guard
```

The full suite needs Bun, and fetching the installer the first time may hit the network. For a quick check only, add `-m "not integration"`,
but that does not mean the install integration test has passed. `--strict-markers` rejects misspelled markers.

The install check uses Skills CLI 1.7.4, a temporary directory, and a project-level install; it does not change the user's global settings.
It installs each skill picked from the collection and compares files and bytes, and also tests selecting multiple skills and installing them all at once.
When upgrading Skills CLI, update the pinned version in both the verification script and the README.

See docs-consistency-guard's [checks](plugins/docs-consistency-guard/skills/docs-consistency-guard/references/checks.md) for check semantics.
When adding a rule, document what can be observed with certainty, its false-positive scope, and the verification step, and add behavior tests.
The example deliberately contains missing targets; update the stored reports when you change it. The skill stays a read-only scanner.

Repository source archives include tests and development files. Skills CLI only
installs a selected skill's directory. Keep this boundary covered by the actual
installer test, not by assuming repository ignore rules filter installed files.
