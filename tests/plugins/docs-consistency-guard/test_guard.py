"""Behavioral contract tests, using sanitized temporary repositories."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "plugins" / "docs-consistency-guard" / "skills" / "docs-consistency-guard" / "scripts"))
import docs_guard as guard

HAS_YAML = importlib.util.find_spec("yaml") is not None


class RepositoryFixture:
    def __init__(self, root):
        self.root = root.resolve()

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def config(self, text, name="mkdocs.yml"):
        self.put(name, text)

    def scan(self, **kwargs):
        return guard.Scanner(self.root).run(**kwargs)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = guard.main(["--root", str(self.root), *args])
        return code, out.getvalue(), err.getvalue()


@pytest.fixture
def repo(tmp_path):
    return RepositoryFixture(tmp_path)


class TestLinks:
    def test_relative_encoded_parent_query_and_image(self, repo):
        repo.put("README.md", '[a](docs/a%20b.md?q=hidden#hello) ![img](docs/img.svg)\n')
        repo.put("docs/a b.md", '[back](../README.md) [local](#anchor) [external](https://example.com/no)\n')
        repo.put("docs/img.svg", "<svg/>")
        result = repo.scan()
        assert result["summary"]["errors"] == 0
        assert len(result["relationships"]) == 3
        assert "hidden" not in json.dumps(result)

    def test_missing_link_line_and_related_target(self, repo):
        repo.put("README.md", '# Project\n\n[guide](docs/missing.md)\n')
        result = repo.scan()
        finding = result["findings"][0]
        assert (finding["rule"], finding["line"], finding["certainty"]) == ("link.missing", 3, "deterministic")
        assert finding["related"] == [{"path": "docs/missing.md", "line": None}]

    def test_full_collapsed_shortcut_reference_links(self, repo):
        repo.put("README.md", '[One][target]\n[target][]\n[target]\n\n[target]: docs/guide.md "Guide"\n')
        repo.put("docs/guide.md", "# Guide\n")
        assert len(repo.scan()["relationships"]) == 3

    def test_angle_destination_with_spaces_and_title(self, repo):
        repo.put("README.md", '[One](<docs/hello world.md> "title")\n')
        repo.put("docs/hello world.md", "# Hello\n")
        assert repo.scan()["summary"]["errors"] == 0
        assert len(repo.scan()["relationships"]) == 1

    def test_code_comments_and_frontmatter_not_reported(self, repo):
        repo.put("README.md", '---\nexample: "[bad](no.md)"\n---\n# Hi\n\n```md\n[bad](a.md)\n```\n\n~~~text\n[bad](b.md)\n~~~\n\n    [bad](c.md)\n\n`[bad](d.md)`\n<!-- [bad](e.md) -->\n[real](missing.md)\n')
        findings = repo.scan()["findings"]
        assert len(findings) == 1
        assert findings[0]["line"] == 18

    def test_external_root_relative_and_anchor_are_skipped(self, repo):
        repo.put("README.md", '[x](https://host/a) [m](mailto:a@example.com) [r](/route) [a](#title) [p](//host/a)\n')
        assert repo.scan()["relationships"] == []

    def test_target_content_is_not_read(self, repo):
        repo.put("README.md", "[source](src/client.py)\n")
        path = repo.put("src/client.py", "")
        path.write_bytes(b"\x00\xff")
        result = repo.scan()
        assert result["summary"]["errors"] == 0
        assert not (result["summary"]["incomplete"])
        assert result["coverage"]["scanned"] == ["README.md"]


class TestSafety:
    def test_symlink_file_is_not_read(self, repo):
        repo.put("outside.txt", "DO-NOT-LEAK")
        (repo.root / "README.md").symlink_to(repo.root / "outside.txt")
        result = repo.scan()
        assert result["summary"]["incomplete"]
        assert "DO-NOT-LEAK" not in json.dumps(result)

    def test_symlink_directory_is_not_followed(self, repo):
        repo.put("other/README.md", "DO-NOT-LEAK")
        (repo.root / "docs").symlink_to(repo.root / "other", target_is_directory=True)
        repo.put("README.md", "[x](docs/README.md)\n")
        result = repo.scan()
        assert "docs/README.md" not in result["coverage"]["scanned"]
        assert result["findings"][0]["rule"] == "link.unsafe"

    def test_encoded_escape_and_sensitive_link_omit_targets(self, repo):
        repo.put("README.md", '[x](%2e%2e/hidden.md) [y](docs/api-token.md?super-secret) [z](%2Fetc/passwd)\n')
        result = repo.scan()
        assert [f["rule"] for f in result["findings"]] == ["link.unsafe"] * 3
        serialized = json.dumps(result)
        assert "super-secret" not in serialized
        assert "api-token" not in serialized

    def test_hidden_sensitive_and_dependency_directories_excluded(self, repo):
        for path in (".env", ".git/README.md", "node_modules/pkg/README.md", "docs/secrets/guide.md", "docs/passwords.md", "docs/private-key.md"):
            repo.put(path, "DO-NOT-LEAK\n[bad](missing.md)")
        repo.put("docs/ordinary.md", "# Safe\n")
        result = repo.scan()
        assert result["coverage"]["scanned"] == ["docs/ordinary.md"]
        assert result["findings"] == []

    def test_oversize_invalid_encoding_and_fifo_are_gaps(self, repo):
        repo.put("README.md", "x" * (guard.MAX_BYTES + 1))
        invalid = repo.put("AGENTS.md", "")
        invalid.write_bytes(b"\xff")
        os.mkfifo(repo.root / "CLAUDE.md")
        result = repo.scan()
        assert result["summary"]["incomplete"]
        assert len(result["coverage"]["skipped"]) == 3

    def test_scan_count_budget_is_incomplete(self, repo, monkeypatch):
        repo.put("docs/a.md", "# A\n")
        repo.put("docs/b.md", "# B\n")
        monkeypatch.setattr(guard, "MAX_FILES", 1)
        assert repo.scan()["summary"]["incomplete"]

    @pytest.mark.parametrize("limit,value", [("MAX_TOTAL_BYTES", 2), ("MAX_ENTRIES", 1)], ids=["total-bytes", "directory-entries"])
    def test_total_and_entry_budgets_are_incomplete(self, repo, monkeypatch, limit, value):
        repo.put("docs/a.md", "Content that exceeds a test-only budget\n")
        monkeypatch.setattr(guard, limit, value)

        result = repo.scan()

        assert result["summary"]["incomplete"]

    def test_secure_read_fails_closed_without_platform_support(self, repo, monkeypatch):
        repo.put("README.md", "# Test\n")
        monkeypatch.setattr(guard.os, "supports_dir_fd", set())
        assert repo.scan()["summary"]["incomplete"]

    def test_root_can_be_user_selected_symlink(self, repo):
        actual = repo.root / "real"
        repo.put("real/README.md", "# Safe\n")
        alias = repo.root / "alias"
        alias.symlink_to(actual, target_is_directory=True)
        assert guard.Scanner(alias).run()["coverage"]["scanned"] == ["README.md"]


@pytest.mark.skipif(not HAS_YAML, reason="optional PyYAML not installed")
class TestMkDocs:
    def test_nested_flow_nav_and_custom_docs_dir(self, repo):
        repo.config('site_name: Test\ndocs_dir: pages\nnav:\n  - Section: [{Home: index.md}, {Missing: absent.md}]\n')
        repo.put("pages/index.md", "# Home\n")
        result = repo.scan()
        assert "pages/index.md" in result["coverage"]["scanned"]
        assert result["summary"]["errors"] == 1
        finding = next(f for f in result["findings"] if f["rule"] == "nav.missing")
        assert finding["line"] is None
        assert finding["related"][0]["path"] == "pages/absent.md"

    def test_custom_config_relative_docs_dir(self, repo):
        repo.config('site_name: Test\ndocs_dir: ../pages\nnav: [index.md]\n', "config/site.yml")
        repo.put("pages/index.md", "# Home\n")
        result = repo.scan(configs=["config/site.yml"])
        assert not (result["summary"]["incomplete"])
        assert result["summary"]["errors"] == 0
        assert result["relationships"][0]["target"] == "pages/index.md"

    def test_nav_absence_and_unlisted_pages_are_valid(self, repo):
        repo.config("site_name: Test\n")
        repo.put("docs/unlisted.md", "# Unlisted\n")
        result = repo.scan()
        assert result["findings"] == []
        assert not (result["summary"]["incomplete"])

    def test_relative_external_nav_is_only_a_candidate(self, repo):
        repo.config('site_name: Test\nnav: [{External: ../host-route/}, {Web: "https://example.com/"}]\n')
        repo.put("docs/index.md", "# Home\n")
        result = repo.scan()
        assert result["summary"]["errors"] == 0
        assert result["findings"][0]["certainty"] == "inference"

    def test_generated_nav_is_candidate(self, repo):
        repo.config('site_name: Test\nplugins: [gen-files]\nnav: [generated.md]\n')
        repo.put("docs/index.md", "# Home\n")
        assert repo.scan()["findings"][0]["certainty"] == "inference"

    @pytest.mark.parametrize("text", [
        'site_name: !ENV TOP_SECRET\n', 'site_name: &x abc\nnav: [*x]\n',
        'INHERIT: ../private.yml\n', 'site_name: A\nsite_name: B\n',
        'nav: [\n', '!!python/object/apply:os.system ["touch SHOULD_NOT_EXIST"]\n',
    ], ids=["env-tag", "alias", "inheritance", "duplicate-key", "malformed", "python-object"])
    def test_tags_aliases_inheritance_duplicates_and_malformed_yaml_are_gaps(self, repo, text):
        repo.config(text)

        result = repo.scan()

        assert result["summary"]["incomplete"]
        assert "TOP_SECRET" not in json.dumps(result)
        assert not (repo.root / "SHOULD_NOT_EXIST").exists()

    @pytest.mark.parametrize("value", ["/etc", "../../outside", "../private", "'C:\\private'", "null"],
                             ids=["absolute", "escape", "sensitive", "windows-drive", "null"])
    def test_unsafe_docs_dirs_are_not_read(self, repo, value):
        repo.config(f"site_name: Test\ndocs_dir: {value}\n")

        result = repo.scan()

        assert result["summary"]["incomplete"]

    def test_nav_missing_directory_and_unsafe_path(self, repo):
        repo.config("site_name: Test\nnav: [folder.md, ../../outside.md]\n")
        (repo.root / "docs/folder.md").mkdir(parents=True)
        result = repo.scan()
        assert {f["rule"] for f in result["findings"]} == {"nav.missing", "nav.unsafe"}

    def test_nav_invalid_type_is_incomplete(self, repo):
        repo.config("site_name: Test\nnav: [123]\n")
        repo.put("docs/index.md", "# Home\n")
        assert repo.scan()["summary"]["incomplete"]

    def test_missing_explicit_config_is_incomplete(self, repo):
        assert repo.scan(configs=["missing.yml"])["summary"]["incomplete"]


class TestSemantics:
    def test_inline_command_identity_is_preserved_for_rules(self, repo):
        repo.put("AGENTS.md", "You must use `npm`.\n")
        repo.put("CLAUDE.md", "You must not use `bun`.\n")
        assert repo.scan()["findings"] == []
        repo.put("CLAUDE.md", "You must not use `npm`.\n")
        assert repo.scan()["findings"][0]["rule"] == "rule.conflict_candidate"

    def test_inline_command_identity_is_preserved_for_duplicates(self, repo):
        repo.put("AGENTS.md", "The recommended command for development is `bun install` before starting work.\n")
        repo.put("CLAUDE.md", "The recommended command for development is `npm install` before starting work.\n")
        assert repo.scan()["findings"] == []

    def test_repeated_prose_is_candidate_with_related_location(self, repo):
        para = "All documentation changes require an explicit review before the next public release.\n"
        repo.put("README.md", "# A\n\n" + para)
        repo.put("AGENTS.md", "# B\n\n" + para.upper())
        finding = repo.scan()["findings"][0]
        assert (finding["rule"], finding["certainty"]) == ("duplicate.paragraph", "inference")
        assert len(finding["related"]) == 1

    def test_normative_opposites_are_candidates_in_both_languages(self, repo):
        repo.put("AGENTS.md", "# Rules\n\nYou must run tests.\n\n必須執行測試。\n")
        repo.put("CLAUDE.md", "# Rules\n\nYou must not run tests.\n\n禁止執行測試。\n")
        result = repo.scan()
        conflicts = [f for f in result["findings"] if f["rule"] == "rule.conflict_candidate"]
        assert len(conflicts) == 2
        assert all(f["certainty"] == "inference" for f in conflicts)
        assert result["summary"]["errors"] == 0

    def test_stale_marker_not_age_or_verdict(self, repo):
        repo.put("README.md", "# Project\n\nLast updated: 2001-01-01\n\nTODO: Check setup\n\n已棄用舊版安裝步驟。\n")
        result = repo.scan()
        assert len(result["findings"]) == 2
        assert result["summary"]["errors"] == 0
        assert all(f["certainty"] == "inference" for f in result["findings"])

    def test_sync_inbound_outbound_literal_and_deleted_path(self, repo):
        repo.put("README.md", "[guide](docs/guide.md)\n")
        repo.put("docs/guide.md", "# Guide\n\nTouch `src/client.py` when changing this workflow.\n")
        report = repo.scan(changed=["docs/guide.md", "src/client.py", "deleted.py"])
        scope = {item["changed"]: item["review"] for item in report["sync_scope"]}
        assert scope["deleted.py"] == []
        assert scope["src/client.py"][0]["path"] == "docs/guide.md"
        assert scope["docs/guide.md"][0]["path"] == "README.md"

    def test_sync_includes_all_members_of_duplicate_group(self, repo):
        para = "Every documentation change requires a coordinated review across the related instruction files.\n"
        for path in ("README.md", "AGENTS.md", "CLAUDE.md"):
            repo.put(path, para)
        result = repo.scan(changed=["README.md"])
        assert {r["path"] for r in result["sync_scope"][0]["review"]} == {"AGENTS.md", "CLAUDE.md"}


@pytest.mark.cli
class TestCLI:
    @pytest.mark.skipif(not HAS_YAML, reason="optional PyYAML not installed")
    @pytest.mark.parametrize("output_format", ["json", "markdown"])
    def test_demo_process_reports_expected_findings_and_sync_scope(self, repo, output_format):
        project = Path(__file__).resolve().parents[3]
        demo = project / "examples/docs-consistency-guard"
        command = [sys.executable, str(Path(guard.__file__).resolve()), "--root", str(demo / "demo"),
                   "--changed", "src/client.py", "--changed", "docs/setup.md", "--format", output_format]

        result = subprocess.run(command, cwd=repo.root, capture_output=True, text=True, timeout=15)

        assert result.returncode == 1
        assert result.stderr == ""
        if output_format == "json":
            expected = json.loads((demo / "report.json").read_text())
            assert json.loads(result.stdout) == expected
        else:
            assert "errors: 2; review candidates: 4; incomplete: false" in result.stdout
            assert "| link.missing | deterministic | docs/setup.md:7 |" in result.stdout
            assert "| nav.missing | deterministic | mkdocs.yml:- |" in result.stdout
            assert "Changed: src/client.py" in result.stdout
            assert "docs/setup.md: literal path mention" in result.stdout

    @pytest.mark.parametrize("content,expected_code", [
        ("TODO: Review intentionally deprecated behavior\n", 0),
        ("[bad](missing.md)\n", 1),
    ], ids=["candidate-only", "missing-source"])
    def test_exit_zero_with_candidates_and_one_with_errors(self, repo, content, expected_code):
        repo.put("README.md", content)

        code, out, err = repo.cli("--format", "json")

        assert code == expected_code
        assert err == ""
        assert json.loads(out)["schema_version"] == "1.0"

    def test_incomplete_overrides_error_exit(self, repo):
        repo.put("README.md", "[bad](missing.md)\n")
        repo.put("AGENTS.md", "x" * (guard.MAX_BYTES + 1))
        code, out, _ = repo.cli("--format", "json")
        assert code == 2
        assert json.loads(out)["summary"]["errors"] == 1

    @pytest.mark.parametrize("path", ["../README.md", "/etc/passwd", "C:\\file", ".env"],
                             ids=["parent-traversal", "absolute", "windows-drive", "hidden"])
    def test_missing_root_and_invalid_changed_paths_exit_two(self, repo, path):
        assert repo.cli("--changed", path)[0] == 2

    def test_missing_root_exits_two(self, repo, capsys):
        code = guard.main(["--root", str(repo.root / "absent")])

        assert code == 2
        assert "invalid input" in capsys.readouterr().err

    def test_report_output_exclusive_and_private(self, repo):
        repo.put("README.md", "# Hello\n")
        output = repo.root / "report.json"
        code, stdout, _ = repo.cli("--format", "json", "--output", str(output))
        assert (code, stdout) == (0, "")
        content = output.read_text()
        assert json.loads(content)["summary"]["documents"] == 1
        assert stat.S_IMODE(output.stat().st_mode) & 0o077 == 0
        assert repo.cli("--output", str(output))[0] == 2
        assert output.read_text() == content

    def test_output_never_overwrites_document_or_follows_symlink(self, repo):
        source = repo.put("README.md", "# Original\n")
        alias = repo.root / "alias.md"
        alias.symlink_to(source)
        assert repo.cli("--output", str(source))[0] == 2
        assert repo.cli("--output", str(alias))[0] == 2
        assert source.read_text() == "# Original\n"

    def test_output_parent_symlink_refused(self, repo):
        (repo.root / "actual").mkdir()
        (repo.root / "alias").symlink_to(repo.root / "actual", target_is_directory=True)
        assert repo.cli("--output", str(repo.root / "alias/report.md"))[0] == 2
        assert not ((repo.root / "actual/report.md").exists())

    def test_read_only_scan_is_reproducible(self, repo):
        repo.put("README.md", "[x](docs/guide.md)\n")
        repo.put("docs/guide.md", "# Guide\n")
        before = {p.relative_to(repo.root).as_posix(): p.read_bytes() for p in repo.root.rglob("*") if p.is_file()}
        first = repo.cli("--format", "json")[1]
        assert first == repo.cli("--format", "json")[1]
        after = {p.relative_to(repo.root).as_posix(): p.read_bytes() for p in repo.root.rglob("*") if p.is_file()}
        assert before == after

    def test_markdown_report_contains_target_without_raw_excerpt(self, repo):
        repo.put("README.md", "Sensitive prose [reference](missing.md?token=DO-NOT-LEAK)\n")
        code, out, _ = repo.cli()
        assert code == 1
        assert "missing.md" in out
        assert "DO-NOT-LEAK" not in out
        assert "Sensitive prose" not in out

    def test_markdown_treats_filename_markup_as_data(self, repo):
        report = guard.Scanner(repo.root).run()
        report["sync_scope"] = [{"changed": "[label](https://host/)\r<b>", "review": []}]
        output = guard.markdown(report)
        assert r"\[label\]\(https://host/\)" in output
        assert "<b>" not in output
        assert "\r" not in output

    def test_real_process_entrypoint(self, repo):
        script = Path(guard.__file__).resolve()
        repo.put("README.md", "[missing](missing.md)\n")
        proc = subprocess.run([sys.executable, str(script), "--root", str(repo.root), "--format", "json"],
                              capture_output=True, text=True, timeout=15)
        assert proc.returncode == 1
        assert json.loads(proc.stdout)["summary"]["errors"] == 1

    def test_missing_yaml_dependency_is_visible(self, repo, monkeypatch):
        repo.put("mkdocs.yml", "site_name: Test\n")
        repo.put("docs/index.md", "# Home\n")
        monkeypatch.setitem(sys.modules, "yaml", None)
        result = repo.scan()
        assert result["summary"]["incomplete"]
        assert "optional" in result["coverage"]["skipped"][0]["reason"]

