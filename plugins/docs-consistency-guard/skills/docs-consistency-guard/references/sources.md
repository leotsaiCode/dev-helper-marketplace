# Official sources and implementation decisions

Reviewed 2026-10-23.

- [Agent Skills specification](https://agentskills.io/specification): a skill is
  a folder with `SKILL.md`, YAML frontmatter including `name` and `description`,
  and Markdown instructions. The name matches the parent directory, uses
  lowercase letters/digits/hyphens, is at most 64 characters, and has no leading,
  trailing or consecutive hyphens. Description is at most 1,024 characters.
  Scripts/references use relative paths; product-specific tool metadata is optional.
- [MkDocs configuration](https://www.mkdocs.org/user-guide/configuration/):
  default config `mkdocs.yml`; `docs_dir` defaults to `docs` and resolves relative
  to the configuration file. An absolute docs_dir is legal upstream but refused
  here. Nav can contain nested sections, Markdown sources and external links;
  missing sources may be interpreted as external relative URLs. `INHERIT`,
  `!ENV`, `!relative`, plugins and hooks need special treatment; the MVP refuses
  unsupported evaluation instead of executing it.
- [MkDocs writing documentation](https://www.mkdocs.org/user-guide/writing-your-docs/):
  links between source Markdown pages are relative to the source file; MkDocs
  rewrites them during rendering. Without explicit nav, MkDocs discovers pages.
  Unlisted pages may still be built. README/index conventions and Markdown
  extensions affect rendering, so a filesystem check does not certify a site.

Recheck these sources when extending YAML support, rendered-route validation,
skill metadata or installation instructions. Record the exact supported subset
in checks.md and test it; avoid inheriting assumptions from one agent vendor.
