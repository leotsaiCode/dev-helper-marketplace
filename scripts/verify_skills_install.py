"""Exercise the real Skills CLI using temporary projects, never global installs."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile

CLI = "skills@1.7.4"
ROOT = Path(__file__).resolve().parents[1]


def files(path):
    result = {}
    for item in path.rglob("*"):
        if item.is_symlink():
            raise AssertionError(f"Unexpected symlink inside skill: {item}")
        if item.is_file():
            result[item.relative_to(path).as_posix()] = item.read_bytes()
    return result


def run(args, cwd):
    env = os.environ.copy()
    env.update(DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", CI="1")
    result = subprocess.run(["bunx", "--bun", CLI, *args], cwd=cwd, env=env,
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def verify():
    if not shutil.which("bunx"):
        raise RuntimeError("Bun/bunx is required for actual Skills CLI verification")
    with tempfile.TemporaryDirectory(prefix="dev-helper-marketplace-install-") as temp:
        base = Path(temp).resolve()
        source = base / "source"
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(
            ".git", ".venv", ".pytest_cache", "dist", "build", "__pycache__", "*.egg-info", "*.pyc", ".DS_Store"))
        skill_paths = {p.parent.name: p.parent for p in source.glob("plugins/*/skills/*/SKILL.md")}
        original = sorted(skill_paths)
        if not original:
            raise AssertionError("No skills discovered")
        # A second plugin/skill exists only in this fixture, not in the product.
        fixture = "distribution-fixture"
        plugin = source / "plugins" / fixture
        extra = plugin / "skills" / fixture
        extra.mkdir(parents=True)
        (extra / "SKILL.md").write_text(
            "---\nname: distribution-fixture\ndescription: Temporary installer test fixture.\n---\n\nRead assets/value.txt.\n",
            encoding="utf-8")
        (extra / "assets").mkdir()
        (extra / "assets/value.txt").write_text("installed resource\n", encoding="utf-8")
        for host in (".claude-plugin", ".codex-plugin"):
            (plugin / host).mkdir()
            (plugin / host / "plugin.json").write_text(json.dumps({
                "name": fixture, "version": "0.1.0", "description": "Installer fixture", "skills": "./skills/"}), encoding="utf-8")
        for catalog in (source / ".claude-plugin/marketplace.json", source / ".agents/plugins/marketplace.json"):
            data = json.loads(catalog.read_text())
            path = "./plugins/" + fixture
            data["plugins"].append({"name": fixture, "source": path if catalog.parent.name == ".claude-plugin" else
                                   {"source": "local", "path": path}})
            catalog.write_text(json.dumps(data), encoding="utf-8")
        skill_paths[fixture] = extra
        listing = run(["add", str(source), "--list"], base)
        for name in original + [fixture]:
            if name not in listing:
                raise AssertionError(f"Skills CLI did not list {name}")

        cases = [("single-" + name, [name], ["--skill", name]) for name in original]
        cases += [("multiple", [original[0], fixture], ["--skill", original[0], fixture]),
                  ("all", original + [fixture], ["--skill", "*"])]
        for label, names, selection in cases:
            project = base / label
            project.mkdir()
            run(["add", str(source), *selection, "--agent", "claude-code", "codex", "--copy", "--yes"], project)
            # Claude receives a copy; Codex uses the shared .agents/skills directory.
            for directory in (project / ".agents/skills", project / ".claude/skills"):
                if sorted(p.name for p in directory.iterdir()) != sorted(names):
                    raise AssertionError(f"Wrong selected skills in {directory}")
                for name in names:
                    expected = files(skill_paths[name])
                    actual = files(directory / name)
                    if actual != expected:
                        raise AssertionError(f"Installed payload differs for {label}/{name}: {sorted(actual)}")
            installed = project / ".agents/skills/docs-consistency-guard"
            if "docs-consistency-guard" in names:
                target = base / "target"
                target.mkdir(exist_ok=True)
                (target / "README.md").write_text("# Existing target\n", encoding="utf-8")
                result = subprocess.run([sys.executable, str(installed / "scripts/docs_guard.py"),
                                         "--root", str(target), "--format", "json"],
                                        cwd=project, capture_output=True, text=True, timeout=15)
                if result.returncode or json.loads(result.stdout)["summary"]["errors"]:
                    raise AssertionError("Installed scanner did not run independently of source repo")
            print(f"PASS {label}: selected skills, exact payloads for Claude/Codex, independent execution")
        print(f"Skills CLI {CLI}: {len(cases)} installation cases passed; no global installs modified.")


if __name__ == "__main__":
    verify()
