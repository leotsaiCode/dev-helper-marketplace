# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Run from the repo root. Python goes through `uv`; the dev-only `test` group provides pytest, and `--extra mkdocs` adds PyYAML.

```sh
# Full suite, including the real Skills CLI install check (needs Bun; may hit the network first time)
uv run --locked --no-editable --group test --extra mkdocs pytest

# Fast suite: skips the install check. Do not report this as full installation validation.
uv run --locked --no-editable --group test --extra mkdocs pytest -m "not integration"

# One plugin / one test / one marker
uv run --locked --no-editable --group test --extra mkdocs pytest tests/plugins/docs-consistency-guard
uv run --locked --no-editable --group test --extra mkdocs pytest "tests/marketplace/test_distribution.py::TestDistribution::test_only_runtime_resources_inside_skills"
uv run --locked --no-editable --group test --extra mkdocs pytest -m cli

# Manifest validation
claude plugin validate .
claude plugin validate plugins/docs-consistency-guard

# Run the scanner (the demo intentionally exits 1)
uv run --no-editable --extra mkdocs docs-consistency-guard --root examples/docs-consistency-guard/demo --format markdown
uv run --isolated --no-project plugins/docs-consistency-guard/skills/docs-consistency-guard/scripts/docs_guard.py --root examples/docs-consistency-guard/clean --format json   # stdlib-only path, as CI runs it
```

pytest runs with `--strict-markers --import-mode=importlib`. Only the `integration` and `cli` markers are registered in `pyproject.toml`. The importlib mode is required because test directories use hyphenated plugin names and are not packages.

## Architecture

This is a multi-plugin marketplace for Claude Code and Codex. Its skills can also be installed one at a time with Skills CLI (`bunx skills@1.7.4`). One source tree serves three distribution channels:

- **Claude plugin**: `.claude-plugin/marketplace.json` → `./plugins/<plugin>` → `.claude-plugin/plugin.json` (`"skills": "./skills/"`).
- **Codex plugin**: `.agents/plugins/marketplace.json` → same plugin dir → `.codex-plugin/plugin.json`.
- **Skills CLI**: discovers `plugins/*/skills/*/SKILL.md` and copies only the selected skill directory.

A fourth channel is unrelated to agent discovery: `pyproject.toml` packages the skill's `docs_guard.py` as the `docs-consistency-guard` console script, using `package-dir` that points into the skill's `scripts/`.

Invariants enforced by `tests/marketplace/test_distribution.py`. Break one and the tests fail:

- The repo root is only a marketplace. Never add a `plugin.json` or `SKILL.md` there.
- Register a new plugin in **both** marketplace files. Its Claude and Codex manifests must share the same name and version. Versions are per plugin.
- A skill directory contains only runtime files: `SKILL.md`, `LICENSE`, `scripts/`, `references/`, and `assets/`. The test asserts the exact file set, so adding a file inside a skill means updating that test.
- A skill must run standalone after install. Use paths relative to the skill dir, never import from the repo root or another skill, and keep skill names unique across the whole repo. The `SKILL.md` `name` must match the folder name.
- No real `SKILL.md` may appear under `tests/`, `docs/`, `examples/`, or `scripts/`. The installer would pick it up.

`scripts/verify_skills_install.py` is the real installer check, wrapped by `tests/marketplace/test_skills_install.py`. It copies the repo to a temp dir, runs pinned Skills CLI 1.7.4 with telemetry off, and compares installed files byte for byte. To bump the CLI version, update this script and the README together.

Test layout: per-plugin tests and fixtures go in `tests/plugins/<plugin>/`. Catalog-level and cross-plugin tests go in `tests/marketplace/`. Tests load `docs_guard` by inserting the skill's `scripts/` dir into `sys.path`.

## docs-consistency-guard specifics

- The scanner is strictly read-only, and the stdlib core must keep working without PyYAML; CI covers both paths. `--output` refuses to overwrite existing files. Exit 2 means the audit was incomplete or could not run, and exit 0 does not certify semantic consistency.
- Findings are either `deterministic` (filesystem observations) or `inference` (review candidates). Rules and their certainty are defined in `references/checks.md`, and filesystem limits in `references/security.md`. When adding a rule, document what is observable, its false-positive scope, and the verification step, and add behavior tests.
- `examples/docs-consistency-guard/demo` contains deliberate errors. When scanner output changes, regenerate `examples/docs-consistency-guard/report.md` and `report.json`.

User-facing docs (README, CONTRIBUTING, `docs/skills/*.md`) are written in English. New skills get a guide at `docs/skills/<skill>.md` linked from the README table. Distribution assumptions and official sources live in `docs/distribution.md`.
