# Distribution contract

Reviewed 2026-10-23. The repository is a multi-plugin marketplace. Plugin roots
live under `plugins/<plugin-name>/`; the repository root has no plugin manifest.

- Skills CLI discovers `plugins/<plugin>/skills/<name>/SKILL.md` and installs selected skill
  directories. Runtime resources must remain inside the selected directory.
  Do not rely on `.gitignore` to filter installation contents.
- Claude marketplace entries point at `./plugins/<name>`. Each plugin has a
  `.claude-plugin/plugin.json` pointing at its own `./skills/` directory.
- Codex entries in `.agents/plugins/marketplace.json` also point at each plugin
  directory. Each plugin carries a `.codex-plugin/plugin.json` compatibility
  manifest; marketplace source paths resolve from repo root.
- Adding a marketplace registers the catalog. Installing a plugin installs only
  that plugin's capabilities, with its own version. Skills CLI can select skills
  across plugin directories. Hosts may still cache the marketplace repository.
- The optional Python distribution exposes the existing CLI. It is separate
  from agent skill discovery. Source archives intentionally retain tests.

Official sources:

- [Skills CLI commands](https://github.com/vercel-labs/skills/blob/main/docs/commands.md)
  for local sources, `--skill`, multiple agents, listing, and `--copy`.
- [Claude plugin manifest](https://code.claude.com/docs/en/plugins-reference)
  and [marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
  for plugin layout and local marketplace distribution.
- [OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins)
  for the supported compatibility manifest and native marketplace format.

Skills CLI 1.7.4 is pinned in the installation verification so the payload
checks are reproducible. The README examples stay unpinned. The verifier works in temporary project
directories and disables installer telemetry. It does not alter global agent
installations or the user's plugin configuration.

Tests use pytest from the development-only `test` dependency group. Per-plugin
tests live in `tests/plugins/<plugin-name>/`; catalog contracts and actual
installer tests live in `tests/marketplace/`. The `integration` marker selects
the real installer check. Running with `-m "not integration"` excludes it and
must not be reported as full installation validation. Tests and pytest remain
outside every installable skill directory.

Local CLI verification establishes installation and file boundaries. It does not
prove model activation quality, marketplace approval, or remote GitHub fetching.
Those require their own tests after a publication destination is chosen.
