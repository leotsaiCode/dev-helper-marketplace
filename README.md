# dev-helper-marketplace

My development helper plugins and Agent Skills. Claude Code and Codex can pick
individual plugins from the marketplace; Skills CLI can go further and pick individual skills.

| Plugin / skill | Purpose | Guide |
| --- | --- | --- |
| [docs-consistency-guard](plugins/docs-consistency-guard/skills/docs-consistency-guard/SKILL.md) | Checks documentation links, MkDocs nav, repeated rules, possible conflict/staleness hints, and documentation sync scope | [Details](docs/skills/docs-consistency-guard.md) |

There is currently one plugin, containing one skill of the same name. Put a new plugin in `plugins/<plugin-name>/`
and register it in both marketplaces; put a new skill in its plugin's `skills/<skill-name>/`.

## Install with Skills CLI

Clone or download this repo first. Run the following from your working project directory, replacing the local path with your checkout path:

```sh
# List available skills
bunx skills@1.7.4 add /absolute/path/to/dev-helper-marketplace --list

# Pick one skill and install it for Claude Code and Codex
bunx skills@1.7.4 add /absolute/path/to/dev-helper-marketplace \
  --skill docs-consistency-guard --agent claude-code codex --copy --yes

# Install every skill in the collection, still only for these two agents
bunx skills@1.7.4 add /absolute/path/to/dev-helper-marketplace \
  --skill '*' --agent claude-code codex --copy --yes
```

Omit `--skill` to choose interactively. Add `--global` to install at the user level.
Once published remotely, the source can be replaced with the actual `OWNER/dev-helper-marketplace`; this project has not set a GitHub owner yet.

Installed content comes only from the selected `plugins/<plugin-name>/skills/<skill-name>/`. docs-consistency-guard currently brings
`SKILL.md`, `scripts/docs_guard.py`, three references, and the MIT `LICENSE`.
`tests/`, `examples/`, the collection README, CI, plugin settings, and Python packaging settings are not inside the skill directory.
Lockfiles or agent install directories created by Skills CLI itself are the installer's own management data.

Skills CLI installs files; it does not install Python or PyYAML for you.
docs-consistency-guard needs Python 3.10+ on Linux/macOS; the MkDocs check also needs PyYAML.
For each agent, choose either the plugin or the standalone skill install, so the same skill is not loaded twice.

## Claude Code plugin

Add the marketplace first, then pick the plugin to install. This installs only docs-consistency-guard:

```sh
claude plugin marketplace add /absolute/path/to/dev-helper-marketplace
claude plugin install docs-consistency-guard@dev-helper-marketplace
```

In Claude Code, use `/docs-consistency-guard:docs-consistency-guard`.
To try it without installing, run `claude --plugin-dir /absolute/path/to/dev-helper-marketplace/plugins/docs-consistency-guard`.
See the [Claude plugin manifest](plugins/docs-consistency-guard/.claude-plugin/plugin.json) for settings.

## Codex plugin

```sh
codex plugin marketplace add /absolute/path/to/dev-helper-marketplace
codex plugin add docs-consistency-guard@dev-helper-marketplace
```

After restarting the session, ask Codex to use `docs-consistency-guard` on a given project.
See the [Codex plugin manifest](plugins/docs-consistency-guard/.codex-plugin/plugin.json) and [Codex marketplace](.agents/plugins/marketplace.json) for settings.
Both hosts install the same plugin, and each plugin is versioned independently. The current plugin provides only skills, with no hooks, MCP servers, or external service connections.
Adding the marketplace does not install every plugin. Plugin hosts may cache the marketplace repo; a Skills CLI install is scoped to the standalone skill directory.

## Layout

```text
dev-helper-marketplace/
├── plugins/
│   └── docs-consistency-guard/
│       ├── .claude-plugin/plugin.json
│       ├── .codex-plugin/plugin.json
│       ├── LICENSE
│       └── skills/
│           └── docs-consistency-guard/
│               ├── SKILL.md
│               ├── LICENSE
│               ├── scripts/docs_guard.py
│               └── references/
├── tests/
│   ├── plugins/docs-consistency-guard/
│   └── marketplace/
├── examples/docs-consistency-guard/
├── docs/skills/
├── scripts/verify_skills_install.py
├── .claude-plugin/marketplace.json
├── .agents/plugins/marketplace.json
└── .github/workflows/ci.yml
```

Each plugin's `skills/` holds only skill runtime resources. Tests and examples stay at the repo level, so installers can take a single skill.
See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add things and the validation rules.

## Development and validation

Run from the repo root:

```sh
# Full validation (includes a real Skills CLI install; needs Bun, may hit the network the first time)
uv run --locked --no-editable --group test --extra mkdocs pytest

# Test a single plugin
uv run --locked --no-editable --group test --extra mkdocs pytest tests/plugins/docs-consistency-guard

# Quick check, excluding the install integration test
uv run --locked --no-editable --group test --extra mkdocs pytest -m "not integration"
claude plugin validate .
claude plugin validate plugins/docs-consistency-guard
```

Tests use pytest: plugin cases go in their own `tests/plugins/<plugin-name>/`,
and marketplace settings and cross-plugin install tests go in `tests/marketplace/`.
pytest is a development test dependency group and is not installed with Skills CLI or the plugin.

The install check is marked with the `integration` marker. It uses the real Skills CLI to install into a temporary project, verifies each skill's file list and contents,
and confirms no tests, examples, plugin, or collection-level settings leak in. It does not modify skills you have already installed;
fetching Skills CLI the first time may need the network. CI runs both the unit tests and this install check.

The terminal tool is still available:

```sh
uv run --no-editable --extra mkdocs docs-consistency-guard \
  --root /path/to/your-repository --format markdown
```

This Python package provides the CLI only and does not register agent skills; install the Agent Skill through Skills CLI or a plugin as described above.

MIT licensed. Packaging assumptions and official sources are recorded in
[docs/distribution.md](docs/distribution.md).
