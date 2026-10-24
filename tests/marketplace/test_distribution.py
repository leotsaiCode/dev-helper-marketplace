"""Check collection contracts independently of optional installers and YAML."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


class TestDistribution:
    def test_only_runtime_resources_inside_skills(self):
        skill = ROOT / "plugins/docs-consistency-guard/skills/docs-consistency-guard"
        actual = {p.relative_to(skill).as_posix() for p in skill.rglob("*") if p.is_file()}
        assert actual == {"SKILL.md", "LICENSE", "scripts/docs_guard.py",
                                  "references/checks.md", "references/security.md", "references/sources.md"}

    def test_skills_are_discoverable_and_self_contained(self):
        assert not ((ROOT / "SKILL.md").exists())
        entries = [p.parent for p in ROOT.glob("plugins/*/skills/*/SKILL.md")]
        assert entries
        assert len(entries) == len({p.name for p in entries}), "Skill names must be globally unique"
        for entry in entries:
            text = (entry / "SKILL.md").read_text()
            assert re.search(r"\A---\nname: " + re.escape(entry.name) + r"\n", text)
            assert (entry / "LICENSE").is_file()
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                resolved = (entry / target.split("#")[0]).resolve()
                assert resolved.is_relative_to(entry.resolve()), target
                assert resolved.exists(), target

    def test_each_plugin_owns_manifests_version_and_skills(self):
        for plugin in (ROOT / "plugins").iterdir():
            if not plugin.is_dir():
                continue
            manifests = [json.loads((plugin / p).read_text()) for p in
                         (".claude-plugin/plugin.json", ".codex-plugin/plugin.json")]
            assert manifests[0] == manifests[1]
            assert manifests[0]["name"] == plugin.name
            assert re.search(r"^\d+\.\d+\.\d+$", manifests[0]["version"])
            assert manifests[0]["skills"] == "./skills/"
            assert (plugin / "skills").is_dir()
            assert (plugin / "LICENSE").is_file()

    def test_marketplace_sources_resolve_to_individual_plugins(self):
        claude = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        codex = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
        for marketplace in (claude, codex):
            assert marketplace["name"] == "dev-helper-marketplace"
            names = [p["name"] for p in marketplace["plugins"]]
            assert len(names) == len(set(names))
            assert set(names) == {p.name for p in (ROOT / "plugins").iterdir() if p.is_dir()}
            for plugin in marketplace["plugins"]:
                source = plugin["source"]
                if isinstance(source, dict):
                    assert source["source"] == "local"
                    source = source["path"]
                assert source == "./plugins/" + plugin["name"]
                assert (ROOT / source).is_dir()

    def test_repo_root_is_only_a_marketplace(self):
        assert not ((ROOT / ".claude-plugin/plugin.json").exists())
        assert not ((ROOT / ".codex-plugin/plugin.json").exists())
        assert not ((ROOT / "plugin.json").exists())
        assert not ((ROOT / "skills").exists())

    def test_no_extra_skill_entrypoints_in_development_files(self):
        for directory in ("tests", "docs", "examples", "scripts"):
            assert list((ROOT / directory).rglob("SKILL.md")) == []

