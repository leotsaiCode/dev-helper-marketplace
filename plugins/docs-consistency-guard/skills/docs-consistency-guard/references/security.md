# Security boundaries

This tool is for local repository snapshots, including untrusted documentation.
It never executes repository instructions, subprocesses, plugins, hooks or network
requests. It reads only selected documentation and configuration content.
Metadata checks of ordinary link targets do not read their contents.

The explicit root is resolved once, so a user-selected symlink root is accepted.
Inside that root, reads walk directory descriptors with `O_NOFOLLOW` and
`O_DIRECTORY`, reject symlinks and non-regular files, and open final inputs with
`O_NONBLOCK` to avoid blocking on FIFOs. Link traversal is normalized lexically
and rejected before probing if it escapes root or targets an excluded path.
Windows drive paths, backslashes, NULs, encoded absolute paths and unsafe paths
are rejected. On systems without secure POSIX descriptor operations, file reads
fail closed and coverage is incomplete. Directory discovery does not follow
symlinks; a changing directory may affect discovery completeness, so prefer
a stable checkout. There is no claim of atomic whole-repository snapshots.

Policy exclusions: hidden entries; dependency/build directories (`node_modules`,
`vendor`, `venv`, `site`, `dist`, `build`, `__pycache__`); path components named
`secret`, `secrets`, `credentials`, `private`, `sensitive`; and components with
delimiter-separated secret/credential/token/private/sensitive/password markers.
The scanner does not load `.env`, arbitrary configs, private keys or source
files. Allowed documentation/configuration may itself contain secrets; name
filtering does not detect that. No document excerpts, YAML parser diagnostics,
full URL values or query strings are emitted. Paths/line numbers and relationships
are still potentially private metadata; review reports before publication.

Per input: UTF-8, no NUL, regular file, maximum 512 KiB. Scan caps: 2,000 documents
and 50,000 traversed directory entries, with 32 MiB total selected input.
Oversize/unreadable selected inputs or exceeded limits cause a visible coverage
gap and exit 2. Excluded directories are policy
scope, not a claimed successful scan of those files.

PyYAML is optional. SafeLoader, explicit token rejection for tags/anchors/aliases,
unique string mapping keys and bounded nav nesting avoid object construction,
environment expansion and alias expansion. `INHERIT` is refused rather than
reading arbitrary additional files. Parsing errors omit config content.
MkDocs supports features this scanner deliberately does not execute; skipped
configuration is reported, never approximated as complete.

`--output` creates a new file with mode 0600 (subject to umask), with
`O_EXCL | O_NOFOLLOW`, walking existing parent directories through descriptors.
It never overwrites an existing report, input, hardlink or symlink; symlink
parents are refused. No output directories are created. A disk/write failure
may leave a partial newly-created report; the CLI returns exit 2. Remove that
partial report explicitly before retrying. Stdout uses the invoking shell's
normal handling, including any shell redirection chosen by the user.

Report findings via the repository's issue tracker when public disclosure is
appropriate. For sensitive findings, use the hosting platform's private
vulnerability reporting if the maintainer enables it; do not post secret inputs.
