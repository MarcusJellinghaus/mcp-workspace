# File access

How the file tools confine paths, and how a `.mcp-file-access` rules file overrides the gitignore default. [SECURITY.md](../SECURITY.md) lists what is enforced.

## Path Confinement

Every path is validated against the project directory before any file operation. Validation resolves symlinks and rejects the path if the resolved location lies outside the project directory. A `..` segment is rejected outright rather than followed. Reference projects are validated the same way against their own directory.

Two kinds of path are rejected that earlier versions accepted:

- **A `..` segment anywhere in the path**, not only a leading one. `read_file("src/../README.md")` is rejected; use `read_file("README.md")`.
- **A path that leaves the project through a symlink.** A symlinked file inside the project whose target is outside it, or an intermediate symlinked directory component, is rejected even though the path contains no `..`. To read content that lives outside the project, configure it with `--reference-project` (read-only) or run a second server instance pointed at it.

One limitation: if the operating system cannot resolve a path at all, validation falls back to the lexical checks alone — the path must contain no `..` and must lie under the project directory by name — so a symlink pointing outside the project is not detected in that case.

File tools also refuse `.git` entries and gitignored paths:

- **`.git`**: A path naming a `.git` file or directory at any depth, in any letter case or Windows alias, or resolving to one through a link, is rejected. So is deleting or moving a whole directory that contains one.
- **Gitignored paths**: Paths matched by the gitignore rules are hidden, including a link into a gitignored location, unless `.mcp-file-access` exposes them — see [Access rules](#access-rules-mcp-file-access). The rules come from every `.gitignore` from the project root down plus `.git/info/exclude` (also for a worktree or submodule checkout), with git's precedence: a deeper file overrides a shallower one, the last matching line wins, and a `.gitignore` inside an ignored directory is not read. Reference projects apply their own rules the same way.
- **Listing an ignored directory** is refused, unless the [walk scope](#access-rules-mcp-file-access) reaches it; it then shows only the exposed paths. A directory whose files are all ignored lists as empty.

Known differences from git:

- `project_dir` is the root: no `.gitignore` above it is read, nor the `info/exclude` of an enclosing repository.
- A nested repository or submodule checkout inside `project_dir` gets the outer rules; its own `info/exclude` is not read.
- Ignore rules apply to committed files too.
- Global excludes (`core.excludesFile`) are not applied.
- A path that does not exist yet is refused by a directory-only rule: under `out/`, a new `out` is refused even though git would ignore it only as a directory.

The `git` tool checks its arguments separately. Paths must be relative and stay inside the repository, and `fetch` and `ls_remote` accept only configured remote names. See [SECURITY.md](../SECURITY.md#intended-restrictions).

## Access rules (`.mcp-file-access`)

A `.mcp-file-access` file at the project root overrides the gitignore default per path. Each line is `<level> <pattern>`:

```
# <level> <gitignore pattern>; last match wins
read-write  /.scratch/
read-only   /.mcp.json
read-only   /uv.lock
```

- Levels: `read-only`, `read-write`. Patterns use gitignore syntax relative to the project root.
- The last matching line wins, so exceptions work in both directions: `read-only config/` then `read-write config/local.json`.
- `#` comments and blank lines are allowed. A `!` negation is invalid; the level replaces it.
- No file means no rules: gitignore alone decides.

Effective access:

| Rule | Path would be committed | Path is gitignored |
|---|---|---|
| (no match) | read-write | hidden |
| `read-only` | read-only | readable, listed (walk scope) |
| `read-write` | read-write | read-write, listed (walk scope), never committed |

Built in, not overridable:

- `.mcp-file-access` itself is read-only, also when it does not exist: the file tools can neither create nor change it.
- `.git` stays refused whatever the rules say.

A path is checked under every spelling the gitignore check uses (as given, canonical, through links); the most restrictive result wins, so `.MCP.json` on Windows or a symlink cannot bypass a rule.

**Directory rules expose everything below them**, including files other gitignore rules ignore (`config/.env`, `__pycache__/`). Prefer narrow, anchored patterns.

**Walk scope.** Reading a path honours a matching rule at any depth. Listing and searching descend into an ignored directory only when a rule matches that directory itself, or an anchored rule's literal prefix leads into it. A deeper match of an unanchored rule is readable by exact path but neither listed nor searched. With `logs/` and `*.log` gitignored:

- `read-only /logs/` — files under `logs/` are listed, found by `search_files` and readable; every write tool refuses them.
- `read-only *.log` — `logs/app.log` is readable by exact path, but neither listed nor searched: the walk never enters the ignored `logs/`.

**Listing.** `list_directory` marks file lines whose access differs from the default with ` (read-only)` or ` (read-write, not committed)`; strip the suffix before passing the path to another tool. Collapsed `dir/ (N files)` lines and `dirs_only` output stay unmarked. `search_files`, `list_reference_directory` and `search_reference_files` include exposed paths, unmarked. `check_file_size` still excludes every gitignored file, exposed or not.

**Refusals.** A write to a read-only path fails with:

```
No write access to '<path>' (rule '<pattern>' in .mcp-file-access)
```

The rules file itself gives `(built-in)` instead of the rule. Reading a hidden path keeps the gitignore message. `move_file` and `delete_directory` check every file in the tree — see [Move File](../README.md#move-file) and [Delete Directory](../README.md#delete-directory).

**Invalid rules file** — an unknown level, an unparsable line or pattern, a `!` negation, an unreadable or non-UTF-8 file, or a directory at that path. The server fails safe: every write is refused, no gitignored path is exposed, and reads of non-ignored files still work. The problems are reported:

- in the write error: `No write access to '<path>' (.mcp-file-access is invalid: line 3: unknown level 'readonly')`;
- as the first line of `list_directory` output (outside its line cap) and of `list_reference_directory` output: `WARNING: .mcp-file-access is invalid (<problems>) - writes are refused and no gitignored path is exposed.` No suffixes are shown while the file is invalid;
- as a log warning, once per distinct problem.

The file is re-read on every tool call, so a fix applies without a restart. Reference projects apply their own `.mcp-file-access`; there both levels mean readable.

**Not a sandbox.** The rules cover the MCP file tools only. A client's native file and shell tools (e.g. Claude Code's `Write`, `Edit`, `Bash`) bypass them, and so do the git tools: `git show HEAD:<path>` prints any committed file, and switching branches with `git_branch` rewrites tracked files. Use the client's own deny rules for native tools.
