#!/usr/bin/env python3
"""Bounded, read-only repository documentation audit. No network or subprocesses."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from urllib.parse import unquote, urlsplit

MAX_BYTES = 512 * 1024
MAX_FILES = 2000
MAX_ENTRIES = 50000
MAX_TOTAL_BYTES = 32 * 1024 * 1024
NAMES = {"README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md"}
CONFIGS = {"mkdocs.yml", "mkdocs.yaml"}
EXCLUDED = {"node_modules", "vendor", "venv", "site", "dist", "build", "__pycache__",
            "secrets", "secret", "credentials", "private", "sensitive"}
SENSITIVE = re.compile(r"(?:^|[._-])(?:secret|secrets|credentials?|tokens?|private|sensitive|passwords?)(?:[._-]|$)", re.I)
MD_EXT = {".md", ".markdown", ".mdown", ".mkdn", ".mkd"}


class BoundaryError(ValueError):
    """Path, size, type or encoding outside the scanner's safe input contract."""


def relative_name(value: str) -> str:
    """Normalize a user-supplied repository-relative path, never a URL."""
    if not value or "\\" in value or "\x00" in value or re.match(r"^[A-Za-z]:", value):
        raise BoundaryError("expected a repository-relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise BoundaryError("absolute paths and parent traversal are not accepted")
    return path.as_posix()


def blocked(parts) -> bool:
    return any(p.startswith(".") or p.lower() in EXCLUDED or SENSITIVE.search(p) for p in parts)


def normalize_link(base: str, value: str) -> str | None:
    """Resolve a local URL lexically, before any filesystem access."""
    try:
        url = urlsplit(value)
    except ValueError as exc:
        raise BoundaryError("malformed link URL") from exc
    if url.scheme or url.netloc or value.startswith(("/", "#")) or not url.path:
        return None
    decoded = unquote(url.path)
    if "\\" in decoded or "\x00" in decoded or decoded.startswith("/") or re.match(r"^[A-Za-z]:", decoded):
        raise BoundaryError("unsafe encoded or platform-specific path")
    parts = list(PurePosixPath(base).parts) if base != "." else []
    for part in decoded.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise BoundaryError("link escapes the repository")
            parts.pop()
        else:
            parts.append(part)
    if blocked(parts):
        raise BoundaryError("link targets an excluded or sensitive path")
    return "/".join(parts) or "."


class Repository:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise BoundaryError("root must be a directory")

    def open_fd(self, name: str) -> int:
        """Walk directory descriptors with O_NOFOLLOW; fail closed without support."""
        relative_name(name)
        if blocked(PurePosixPath(name).parts):
            raise BoundaryError("excluded or sensitive path")
        if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
            raise BoundaryError("secure directory-relative reads require a POSIX platform")
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            parts = PurePosixPath(name).parts
            for i, part in enumerate(parts):
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                if i < len(parts) - 1:
                    flags |= os.O_DIRECTORY
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except BaseException:
            os.close(fd)
            raise

    def read(self, name: str) -> str:
        fd = self.open_fd(name)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise BoundaryError("not a regular file or exceeds 512 KiB")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES or b"\x00" in data:
                raise BoundaryError("oversize or binary input")
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise BoundaryError("input is not UTF-8") from exc
        finally:
            os.close(fd)

    def target(self, name: str) -> str:
        try:
            fd = self.open_fd(name)
        except FileNotFoundError:
            return "missing"
        except (OSError, BoundaryError):
            return "blocked"
        try:
            mode = os.fstat(fd).st_mode
            return "file" if stat.S_ISREG(mode) else "directory" if stat.S_ISDIR(mode) else "blocked"
        finally:
            os.close(fd)


def prose(text: str, mask_inline: bool = True) -> str:
    """Mask frontmatter, comments, fenced and inline code, preserving line numbers."""
    lines = text.splitlines(keepends=True)
    front = bool(lines and lines[0].strip() == "---")
    fence = None
    result = []
    for i, line in enumerate(lines):
        if front:
            result.append("\n")
            if i and line.strip() in {"---", "..."}:
                front = False
            continue
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if match:
            mark = match[1]
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence) and not line[match.end():].strip():
                fence = None
            result.append("\n")
        elif fence or line.startswith(("    ", "\t")):
            result.append("\n")
        else:
            result.append(line)
    value = "".join(result)
    value = re.sub(r"<!--[\s\S]*?-->", lambda m: "\n" * m[0].count("\n"), value)
    return re.sub(r"(`+)([^\n]*?)\1", lambda m: " " * len(m[0]), value) if mask_inline else value


# ponytail: conservative Markdown subset; unsupported constructs are coverage notes,
# not a claim of full CommonMark or renderer compatibility.
INLINE_LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(?:<([^>\n]*)>|([^\s()]+))(?:\s+[\"'][^\n]*?[\"'])?\s*\)")
DEFINITION = re.compile(r"^\s{0,3}\[([^\]\n]+)\]:\s*(?:<([^>\n]+)>|(\S+))", re.M)
REFERENCE = re.compile(r"!?\[([^\]\n]+)\](?:\[([^\]\n]*)\])?(?![\[(])")


def links(text: str):
    definitions = {" ".join(m[1].split()).casefold(): m[2] or m[3] for m in DEFINITION.finditer(text)}
    for match in INLINE_LINK.finditer(text):
        yield text.count("\n", 0, match.start()) + 1, match[1] or match[2] or ""
    masked = INLINE_LINK.sub(lambda m: " " * len(m[0]), text)
    masked = DEFINITION.sub(lambda m: " " * len(m[0]), masked)
    for match in REFERENCE.finditer(masked):
        key = " ".join((match[2] or match[1]).split()).casefold()
        if key in definitions:
            yield text.count("\n", 0, match.start()) + 1, definitions[key]


def load_config(text: str):
    try:
        import yaml
    except ImportError as exc:
        raise BoundaryError("MkDocs YAML requires the optional mkdocs extra (PyYAML)") from exc

    class Loader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            seen = set()
            for key, _ in node.value:
                value = self.construct_object(key, deep=deep)
                if not isinstance(value, str) or value in seen:
                    raise BoundaryError("YAML mapping keys must be unique strings")
                seen.add(value)
            return super().construct_mapping(node, deep=deep)

    try:
        for token in yaml.scan(text):
            if isinstance(token, (yaml.tokens.TagToken, yaml.tokens.AnchorToken, yaml.tokens.AliasToken)):
                raise BoundaryError("YAML tags, anchors and aliases are not evaluated")
        config = yaml.load(text, Loader=Loader)
    except (yaml.YAMLError, RecursionError, ValueError, TypeError) as exc:
        if isinstance(exc, BoundaryError):
            raise
        raise BoundaryError("invalid or unsupported YAML; content omitted") from exc
    if not isinstance(config, dict):
        raise BoundaryError("MkDocs configuration must be a mapping")
    if "INHERIT" in config:
        raise BoundaryError("MkDocs INHERIT is not evaluated; review the effective config manually")
    return config


def nav_leaves(nav, depth=0):
    if depth > 32:
        raise BoundaryError("nav exceeds 32 nesting levels")
    if isinstance(nav, str):
        yield nav
    elif isinstance(nav, list):
        for item in nav:
            yield from nav_leaves(item, depth + 1)
    elif isinstance(nav, dict):
        for value in nav.values():
            yield from nav_leaves(value, depth + 1)
    elif nav is not None:
        raise BoundaryError("nav entries must be strings, lists or title mappings")


class Scanner:
    def __init__(self, root: Path):
        self.repo = Repository(root)
        self.documents = {}
        self.findings = []
        self.edges = []
        self.skipped = []
        self.incomplete = False
        self.docs_dirs = {"docs"}
        self.total_bytes = 0

    def add(self, rule, path, line, message, certainty="deterministic", severity="warning", related=None):
        self.findings.append(dict(rule=rule, certainty=certainty, severity=severity,
                                  path=path, line=line, message=message, related=related or []))

    def gap(self, path, reason):
        self.incomplete = True
        self.skipped.append(dict(path=path, reason=reason))

    def read(self, name):
        try:
            text = self.repo.read(name)
            self.total_bytes += len(text.encode("utf-8"))
            if self.total_bytes > MAX_TOTAL_BYTES:
                raise BoundaryError("total selected input exceeds 32 MiB")
            return text
        except (OSError, BoundaryError) as exc:
            self.gap(name, str(exc) if isinstance(exc, BoundaryError) else "unreadable, missing or unsafe filesystem entry")
            return None

    def mkdocs(self, name):
        text = self.read(name)
        if text is None:
            return
        try:
            config = load_config(text)
            directory = config.get("docs_dir", "docs")
            if not isinstance(directory, str):
                raise BoundaryError("docs_dir must be a string")
            # Absolute docs_dir is valid MkDocs, but outside this tool's safety contract.
            if PurePosixPath(directory).is_absolute():
                raise BoundaryError("absolute docs_dir is not scanned")
            docs_dir = normalize_link(str(PurePosixPath(name).parent), directory)
            if docs_dir is None:
                raise BoundaryError("docs_dir must be a local repository-relative directory")
            state = self.repo.target(docs_dir)
            if state != "directory":
                raise BoundaryError("docs_dir is missing, unsafe or not a directory")
            self.docs_dirs.add(docs_dir)
            values = list(nav_leaves(config.get("nav")))
        except (BoundaryError, RecursionError) as exc:
            self.gap(name, str(exc) if isinstance(exc, BoundaryError) else "configuration nesting limit exceeded")
            return
        dynamic = bool(config.get("plugins") or config.get("hooks"))
        for value in values:
            try:
                target = normalize_link(docs_dir, value)
            except BoundaryError:
                self.add("nav.unsafe", name, None, "Nav target is outside the permitted path boundary; target omitted.")
                continue
            if target is None:
                continue
            self.edges.append(dict(source=name, target=target, line=None, kind="nav"))
            state = self.repo.target(target)
            if state == "blocked":
                self.add("nav.unsafe", name, None, "Nav target is a symlink, sensitive path or unsupported filesystem entry.")
            elif state != "file":
                # MkDocs accepts relative external links and plugins can generate pages.
                definite = PurePosixPath(target).suffix.lower() in MD_EXT and not dynamic
                self.add("nav.missing", name, None,
                         "No local source file at nav target. Confirm relative external URLs or generated pages before changing nav.",
                         "deterministic" if definite else "inference", "error" if definite else "warning",
                         [dict(path=target, line=None)])

    def discover(self):
        count = 0
        selected_count = 0
        def onerror(_):
            self.gap(".", "directory traversal could not inspect all entries")
        for parent, dirs, files in os.walk(self.repo.root, followlinks=False, onerror=onerror):
            rel = Path(parent).relative_to(self.repo.root)
            count += len(dirs) + len(files)
            if count > MAX_ENTRIES:
                self.gap(".", "repository traversal exceeds 50000 entries")
                return
            dirs[:] = sorted(d for d in dirs if not blocked((d,)) and not (Path(parent) / d).is_symlink())
            for filename in sorted(files):
                path = (rel / filename).as_posix()
                in_docs = any(path.startswith(d + "/") or d == "." for d in self.docs_dirs)
                selected = filename in NAMES or (in_docs and Path(filename).suffix.lower() in MD_EXT)
                if not selected or blocked(PurePosixPath(path).parts):
                    continue
                selected_count += 1
                if selected_count > MAX_FILES or self.total_bytes > MAX_TOTAL_BYTES:
                    self.gap(".", "document count or total input budget exceeded")
                    return
                text = self.read(path)
                if text is not None:
                    self.documents[path] = text

    def check_links(self):
        for path, raw in self.documents.items():
            for line, value in links(prose(raw)):
                try:
                    target = normalize_link(str(PurePosixPath(path).parent), value)
                except BoundaryError:
                    self.add("link.unsafe", path, line, "Link crosses the permitted path boundary; target omitted.")
                    continue
                if target is None:
                    continue
                self.edges.append(dict(source=path, target=target, line=line, kind="link"))
                state = self.repo.target(target)
                if state == "missing":
                    self.add("link.missing", path, line, "Relative link has no local filesystem target (source-path check only).",
                             severity="error", related=[dict(path=target, line=None)])
                elif state == "blocked":
                    self.add("link.unsafe", path, line, "Link targets a symlink or unsupported filesystem entry; not followed.")

    def semantics(self):
        paragraphs = defaultdict(list)
        rules = defaultdict(lambda: {True: [], False: []})
        for path, raw in self.documents.items():
            # Inline commands carry rule meaning: never erase npm/bun/version tokens.
            text = prose(raw, mask_inline=False)
            marker_lines = prose(raw).splitlines()
            for match in re.finditer(r"[^\n]+(?:\n(?!\s*\n)[^\n]+)*", text):
                value = " ".join(match[0].split()).casefold()
                if len(value) >= 40 and not value.startswith("#"):
                    key = hashlib.sha256(value.encode()).hexdigest()
                    paragraphs[key].append(dict(path=path, line=text.count("\n", 0, match.start()) + 1))
            for line, value in enumerate(text.splitlines(), 1):
                if re.search(r"\b(todo|fixme|outdated|obsolete|deprecated)\b|待更新|已過時|可能過時|已棄用", marker_lines[line - 1], re.I):
                    self.add("stale.candidate", path, line,
                             "Maintenance/deprecation marker found; it may be intentional. Verify current behavior and ownership.", "inference")
                # Exact action matching intentionally avoids claiming to understand scope or precedence.
                match = re.match(r"\s*(?:[-*+]\s+)?(?:you\s+)?(must not|must|never|always|禁止|不得|不要|必須|務必)\s*(.+)", value, re.I)
                if match:
                    negative = match[1].casefold() in {"must not", "never", "禁止", "不得", "不要"}
                    action = " ".join(match[2].strip(" .。!！").casefold().split())
                    if action:
                        rules[action][negative].append(dict(path=path, line=line))
        for group in paragraphs.values():
            if len(group) > 1:
                first, *rest = group
                self.add("duplicate.paragraph", first["path"], first["line"],
                         "Normalized prose paragraph repeats. Decide whether to consolidate or retain intentional repetition.",
                         "inference", related=rest)
                for other in rest:
                    self.edges.append(dict(source=first["path"], target=other["path"], line=first["line"], kind="duplicate"))
        for polarities in rules.values():
            if polarities[True] and polarities[False]:
                first = polarities[False][0]
                related = polarities[True] + polarities[False][1:]
                self.add("rule.conflict_candidate", first["path"], first["line"],
                         "Opposite normative wording for the same normalized action. Check scope, exceptions and instruction precedence.",
                         "inference", related=related)
                for other in related:
                    self.edges.append(dict(source=first["path"], target=other["path"], line=first["line"], kind="rule"))

    def sync(self, changed):
        items = []
        for change in sorted(set(changed)):
            affected = defaultdict(set)
            for finding in self.findings:
                if finding["rule"] not in {"duplicate.paragraph", "rule.conflict_candidate"}:
                    continue
                group = {finding["path"]} | {r["path"] for r in finding["related"]}
                if change in group:
                    for path in group - {change}:
                        affected[path].add("shared " + finding["rule"])
            for edge in self.edges:
                if edge["target"] == change and edge["source"] != change:
                    affected[edge["source"]].add("incoming " + edge["kind"])
                if edge["source"] == change and edge["target"] in self.documents and edge["target"] != change:
                    affected[edge["target"]].add("outgoing " + edge["kind"])
            for path, raw in self.documents.items():
                if path != change and re.search(r"(?<![\w./-])" + re.escape(change) + r"(?![\w./-])", raw):
                    affected[path].add("literal path mention (candidate)")
            items.append(dict(changed=change, review=[dict(path=p, reasons=sorted(r)) for p, r in sorted(affected.items())]))
        return items

    def run(self, configs=None, changed=()):
        if configs is None:
            configs = sorted(n for n in CONFIGS if os.path.lexists(self.repo.root / n))
        for name in configs:
            self.mkdocs(name)
        self.discover()
        self.check_links()
        self.semantics()
        self.findings.sort(key=lambda f: (f["path"], f["line"] or 0, f["rule"]))
        errors = sum(f["certainty"] == "deterministic" and f["severity"] == "error" for f in self.findings)
        return dict(schema_version="1.0", summary=dict(documents=len(self.documents), findings=len(self.findings), errors=errors,
                    candidates=sum(f["certainty"] == "inference" for f in self.findings), incomplete=self.incomplete),
                    coverage=dict(scanned=sorted(self.documents), configs=configs, skipped=self.skipped,
                                  limitations=["Conservative Markdown subset; no HTML, nested-parenthesis destinations, anchors, external URLs or rendered routes checked.",
                                               "No code/version/git-age verification; semantic results are review candidates only.",
                                               "Hidden, sensitive, dependency/build directories and directory symlinks excluded by policy.",
                                               "No MkDocs plugins, hooks, inheritance, environment expansion, exclude_docs or generated routes evaluated."]),
                    findings=self.findings, relationships=self.edges, sync_scope=self.sync(changed))


def markdown(report):
    def cell(value):
        value = re.sub(r"[\x00-\x1f\x7f]", " ", str(value))
        value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return re.sub(r"([\\`*\[\]()!|])", r"\\\1", value)
    s = report["summary"]
    lines = ["# Documentation consistency report", "", f"Documents: {s['documents']}; errors: {s['errors']}; review candidates: {s['candidates']}; incomplete: {str(s['incomplete']).lower()}.", "",
             "| Check | Certainty | Location | Observation | Related locations |", "| --- | --- | --- | --- | --- |"]
    for f in report["findings"]:
        related = ", ".join(f"{r['path']}:{r['line'] or '-'}" for r in f["related"])
        lines.append("| " + " | ".join(cell(x) for x in (f["rule"], f["certainty"], f"{f['path']}:{f['line'] or '-'}", f["message"], related)) + " |")
    lines += ["", "## Coverage", ""]
    lines += ["- " + cell(x) for x in report["coverage"]["limitations"]]
    lines += [f"- Skipped {cell(x['path'])}: {cell(x['reason'])}" for x in report["coverage"]["skipped"]]
    lines += ["", "## Synchronization review scope", "", "Direct relationships and literal mentions only; this is not a complete dependency graph.", ""]
    for item in report["sync_scope"]:
        lines.append("- Changed: " + cell(item["changed"]))
        lines += ["  - " + cell(r["path"]) + ": " + cell(", ".join(r["reasons"])) for r in item["review"]]
    return "\n".join(lines) + "\n"


def write_report(path: Path, content: str):
    """Exclusive creation; never overwrite files or follow output parent symlinks."""
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise BoundaryError("secure output requires a POSIX platform")
    absolute = Path(os.path.abspath(path))
    fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        output = os.open(absolute.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(output, "w", encoding="utf-8") as stream:
            stream.write(content)
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository directory (default: current directory)")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", type=Path, help="create a new report file; existing files and symlink parents rejected")
    parser.add_argument("--mkdocs-config", action="append", help="repository-relative config; repeatable (default: root mkdocs.yml/yaml)")
    parser.add_argument("--changed", action="append", default=[], help="repository-relative changed path for sync review; repeatable")
    args = parser.parse_args(argv)
    try:
        changed = [relative_name(p) for p in args.changed]
        configs = [relative_name(p) for p in args.mkdocs_config] if args.mkdocs_config else None
        if any(blocked(PurePosixPath(p).parts) for p in changed + (configs or [])):
            raise BoundaryError("changed/config paths must not target excluded or sensitive locations")
        report = Scanner(args.root).run(configs, changed)
        content = json.dumps(report, indent=2, ensure_ascii=True) + "\n" if args.format == "json" else markdown(report)
        if args.output:
            write_report(args.output, content)
        else:
            sys.stdout.write(content)
        return 2 if report["summary"]["incomplete"] else 1 if report["summary"]["errors"] else 0
    except (OSError, BoundaryError, RecursionError):
        # Filesystem errors and YAML must never echo repository content or secret URLs.
        sys.stderr.write("docs-consistency-guard: invalid input, unsafe path, unavailable root or output could not be created; see --help.\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
