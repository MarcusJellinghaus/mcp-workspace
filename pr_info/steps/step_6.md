# Step 6 — `ref_snapshot`: reading at `origin/<default>` via GitPython

## LLM prompt

> Read `pr_info/steps/summary.md`, then implement **only** `pr_info/steps/step_6.md`.
> Write the tests first, then the implementation. Use the MCP tools from `.claude/CLAUDE.md`.
> Run pylint, pytest (`extra_args: ["-n", "auto"]`), mypy and lint-imports; all must pass.
> Run `run_format_code`, then make exactly one commit for this step.

## WHERE

- `src/mcp_workspace/git_operations/ref_snapshot.py` (new; nothing else imports it yet)
- `tests/git_operations/test_ref_snapshot.py` (new)

## Preconditions

- Check with `get_library_source` that `git.exc` re-exports `BadName` and `ODBError` from
  `gitdb.exc`; import them from `git.exc`.
- The design relies on `repo.commit("refs/remotes/origin/HEAD")` raising `BadName` when
  `origin/HEAD` is dangling (points at a missing branch). Probe it first (scratch probe, see
  `.claude/CLAUDE.md`). If it raises anything else, write one line to `pr_info/.blocked.txt`
  and stop.

## WHAT

```python
class RefFallback(Enum):
    NOT_A_REPO = "not_a_repo"   # plain folder, broken/incomplete .git, missing path
    NO_DEFAULT = "no_default"   # git repo without origin, or no default ref resolves

@dataclass(frozen=True)
class RefSnapshot:
    repo: Repo
    name: str      # reference project name, for messages
    ref: str       # e.g. "origin/main"
    sha: str       # full SHA, resolved once per call

    @cached_property
    def tree(self) -> Tree: ...            # root tree of `sha`, resolved once per snapshot
    @property
    def where(self) -> str: ...            # "origin/main @ 03d1741"
    def list_files(self) -> list[str]: ...
    def read_bytes(self, path: str, display_path: str | None = None) -> bytes: ...
        # path: from ref_relative_path (tree lookup); display_path: the caller's original
        # file_path, used verbatim in error messages (defaults to path)

@contextmanager
def open_ref_snapshot(path: Path, name: str) -> Iterator[RefSnapshot | RefFallback]: ...
```

## HOW

- Open with `Repo(path, search_parent_directories=False)`; `InvalidGitRepositoryError` /
  `NoSuchPathError` **at open only** → yield `RefFallback.NOT_A_REPO`. Do not wrap the
  `yield` in that `try` (exceptions from the caller's body must pass through untouched).
- Right after opening: `repo.git.update_environment(**GIT_NONINTERACTIVE_ENV)` (before any
  object access). Close with `core._close_repo_safely(repo)` in `finally`.
- Origin check: `any(r.name == "origin" for r in repo.remotes)`; none → `NO_DEFAULT`.
- Resolution uses full ref names only (a short `origin/main` can be shadowed).
- Every GitPython failure (`GitCommandError`, `ODBError`, `ValueError`) is turned into
  `ValueError(scrub_credentials(...))` raised **outside** the `except` block. `FileNotFoundError`
  and `IsADirectoryError` are raised directly. No GitPython exception type leaves this module.
- `list_files` uses `core.run_git_raw(self.repo, "ls_tree", "-r", "-z", self.sha)` and
  `porcelain_parsers.parse_ls_tree_z` — not `traverse()` (breadth-first) and not
  `conflicts.list_tree` (one level, own Repo).
- `read_bytes` reads via the object database (`blob.data_stream.read()`), never via
  `run_git_timed` (it would alter content).
- `tree` = `self.repo.commit(self.sha).tree`, computed on first use and cached on the
  snapshot (`functools.cached_property` writes to the instance `__dict__`, so it works on
  the frozen dataclass; no `__slots__`). Every `read_bytes` lookup reuses it, so a search
  over N files does not re-resolve the commit N times. The snapshot stays pinned to its one
  `sha`. GitPython failures while resolving it map to `ValueError` like the others.

## ALGORITHM

```
_resolve_origin_default(repo):                      # -> (ref_label, sha) | None
    for full in ("refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/master"):
        try: commit = repo.commit(full)
        except BadName: continue                     # missing or dangling → next
        return _label(repo, full), commit.hexsha     # other errors propagate → ValueError
    return None
_label: origin/HEAD → `run_git_raw(repo, "symbolic_ref", "-q", full)` target minus
        "refs/remotes/" (fallback "origin/HEAD"); others → full minus "refs/remotes/"

read_bytes(path, display_path=None):
    shown = display_path if display_path is not None else path   # caller's text, as today
    if path == "": raise IsADirectoryError(f"Path '{shown}' is not a file")
    obj = self.tree[path]  (KeyError → None)     # cached root tree, never re-walked from commit(sha)
    if obj is None or obj.type == "submodule" or obj.mode == 0o120000: raise _not_found(path, shown)
    if obj.type == "tree": raise IsADirectoryError(f"Path '{shown}' is not a file")
    return obj.data_stream.read()

_not_found(path, shown):
    hint = first f in list_files() with f.casefold() == path.casefold()   # lookup on the tree path
    msg = f"File '{shown}' is not in {where} of reference '{name}'"
    return FileNotFoundError(msg + (f"; did you mean '{hint}'?" if hint else "."))

list_files():
    rc, out, err = run_git_raw(repo, "ls_tree", "-r", "-z", sha);  rc != 0 → ValueError(scrubbed err)
    return [e["path"] for e in parse_ls_tree_z(out) if e["type"] == "blob" and e["mode"] != "120000"]
```

## DATA

- Not-found: `File 'src/x.py' is not in origin/main @ 03d1741 of reference 'mcp-workspace'.`
- Case hint: `File 'claude.md' is not in origin/main @ 03d1741 of reference 'mcp-workspace'; did you mean 'CLAUDE.md'?`
- Directory: `Path 'src' is not a file` (`IsADirectoryError`).
- Messages name the caller's `display_path` verbatim (today's `read_file` texts name the
  caller's `file_path`); the case hint names the tree's spelling.

## Tests (write first)

Use the bare-origin fixtures in `tests/conftest.py` (`_origin_remote`, `make_clone`,
`origin_clone`); push upstream changes from a second clone made with `make_clone`.

- Upstream content wins: (a) work clone on a feature branch with a different commit,
  (b) dirty working tree, (c) work clone behind origin after a manual `git fetch` → `read_bytes`
  returns the origin/main bytes; `snap.ref == "origin/main"`, `snap.sha` = origin/main SHA.
- Dangling `origin/HEAD` (`symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/gone`)
  → falls through to `origin/main`.
- Only `refs/remotes/origin/master` present (delete `origin/HEAD` and `origin/main`) →
  `snap.ref == "origin/master"`.
- `NO_DEFAULT`: repo without remotes; repo with `origin` but no remote-tracking refs;
  `.git` with `HEAD`, `objects/`, `refs/` but no `config`.
- `NOT_A_REPO`: plain folder; missing path; empty `.git` dir; `.git` file pointing nowhere;
  `.git` with only `HEAD`; plain folder nested inside a checkout.
- Corrupt: `refs/remotes/origin/HEAD` target file overwritten with a SHA of a missing object
  → `open_ref_snapshot` raises `ValueError` (not a fallback).
- `list_files` order == `git ls-tree -r --name-only <sha>`; a symlink entry
  (`update-index --add --cacheinfo 120000,<blob>,link`) and a gitlink
  (`--cacheinfo 160000,<sha>,sub`) pushed upstream are absent; reading either →
  `FileNotFoundError`.
- `read_bytes` keeps CRLF bytes exactly; not-found message names ref, short SHA and
  reference name; case hint; directory → `IsADirectoryError` "Path 'src' is not a file".
- Exact error texts use `display_path`, parametrised:
  `read_bytes("src/x.py", "src\\x.py")` → `FileNotFoundError` text exactly
  `"File 'src\\x.py' is not in origin/main @ <short> of reference '<name>'."`;
  `read_bytes("src", "./src/")` → `IsADirectoryError` text exactly `"Path './src/' is not a file"`;
  `read_bytes("", "./")` → exactly `"Path './' is not a file"` (never a substituted `'.'`);
  without `display_path`, messages use `path`.
- Missing blob object: push a file upstream, fetch, then delete that blob's loose object
  file (`.git/objects/<sha[:2]>/<sha[2:]>`, the work clone not packed — e.g. fetch from a
  local bare origin with `transfer.unpackLimit` high or use `git unpack-objects`; skip if
  the object stays packed) → `read_bytes(path)` raises `ValueError` (no GitPython
  exception type escapes).
- Root tree resolved once: on one snapshot, call `read_bytes` for three different paths
  with `snap.repo.commit` patched with `wraps=` → called exactly once; `snap.tree` is the
  same object on repeated access.
- `snap.repo.git.environment()` contains `GIT_TERMINAL_PROMPT == "0"`.
- No `git cat-file` process left after the context exits (repo closed): assert
  `_close_repo_safely` is called (patch it with `wraps=`).
