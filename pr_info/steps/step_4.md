# Step 4 — Conformance test against `git check-ignore`

## LLM prompt

> Read `pr_info/steps/summary.md`, this file (`pr_info/steps/step_4.md`) and the "Tests" and
> "Scenarios" sections of issue #392. Steps 1–3 are done. Implement **only** this step:
> test-only unless a scenario needs a small fix to `directory_utils.py` (see Precondition).
> Run pylint, pytest (`-n auto`) and mypy; all must pass. Format, then make exactly one
> commit.

## Precondition

The test needs the `git` binary. If `git --version` is not available to the test run
(GitPython raises `GitCommandNotFound` in a first probe run), write one line to
`pr_info/.blocked.txt` and stop.

If a scenario disagrees with git and is not one of the two known differences below, fix
the cause in `directory_utils.py` within this step if it is small and local; otherwise write
one line naming the scenario to `pr_info/.blocked.txt` and stop.

## WHERE

- `tests/file_tools/test_gitignore_conformance.py` (new)

## WHAT

```python
pytestmark = pytest.mark.git_integration

@dataclass(frozen=True)
class Scenario:
    rules: dict[str, str]                 # rule-file path -> content (".gitignore", "sub/.gitignore", ".git/info/exclude")
    queries: tuple[str, ...]
    create_files: bool = True             # False for case 23 (paths don't exist)
    known_diff: frozenset[str] = frozenset()
    global_excludes: str = ""             # case 18 only

SCENARIOS: dict[str, Scenario] = {"01": ..., ..., "25": ...}

@pytest.fixture
def git_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path: ...   # returns the global config file
def _git_ignored(repo_dir: Path, paths: Sequence[str]) -> set[str]: ...
def _build(root: Path, scenario: Scenario, git_config: Path) -> None: ...

@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_matches_git(name: str, tmp_path: Path, git_env: Path) -> None: ...
def test_worktree_info_exclude(tmp_path: Path, git_env: Path, monkeypatch: pytest.MonkeyPatch) -> None: ...
@pytest.mark.parametrize("relative", [False, True])
def test_submodule_info_exclude(tmp_path: Path, git_env: Path, relative: bool) -> None: ...
```

## HOW

- `git_env`: `home = tmp_path / "home"`; empty `home / "gitconfig"`;
  `monkeypatch.setenv` for `GIT_CONFIG_GLOBAL` (that file), `GIT_CONFIG_NOSYSTEM=1`,
  `HOME`, `XDG_CONFIG_HOME` (`home / ".config"`).
- `_build`: `Repo.init(root)`; write each rule file (overwrite `.git/info/exclude`); if
  `create_files`, create every query as a file unless it is a rule file or a parent of
  another query (those are directories). For `global_excludes`, write the patterns to a file
  and set `core.excludesFile` to it in the global config file.
- `_git_ignored`: write `b"\0".join(paths) + b"\0"` to `tempfile.TemporaryFile()`, `seek(0)`,
  then `Repo(repo_dir).git.check_ignore("--no-index", "--stdin", "-z", istream=f,
  with_extended_output=True, with_exceptions=False, stdout_as_string=False)`.
  Assert `status <= 1` (1 = none ignored). Split stdout on `b"\0"`, decode, drop empties.
  Never `io.BytesIO` (no `fileno()` → misleading `GitCommandNotFound`), never text mode
  (`\r\n` on Windows turns every answer into "not ignored").
- Imports: `from git import Repo` (tests only; GitPython is never imported from `file_tools`).

## ALGORITHM

`test_matches_git`:
```
s = SCENARIOS[name]; root = tmp_path / "repo"; _build(root, s, git_env)
by_git = _git_ignored(root, s.queries); listed = set(list_files(".", root))
for q in s.queries:
    expected = (q in by_git) != (q in s.known_diff)
    assert is_path_gitignored(q, root) is expected, q
    if (root / q).is_file(): assert (q not in listed) is expected, q
```
Case 22 differs by OS (`core.ignorecase`); git is the oracle — no hard-coded values.

## DATA — scenarios (from the issue)

| # | rules | queries | notes |
|---|---|---|---|
| 01 | root `*.env` | `a.env`, `sub/a.env`, `sub/ok.txt` | |
| 02 | root `secret/` | `secret`, `secret/key.txt`, `other/secret` | `secret` is a dir |
| 03 | root `/build` | `build/x`, `sub/build/x` | |
| 04 | root `docs/tmp` | `docs/tmp/x`, `sub/docs/tmp/x` | |
| 05 | root `**/logs` | `logs/a`, `x/y/logs/a` | |
| 06 | root `a/**/b` | `a/b/f`, `a/x/y/b/f`, `x/a/b/f` | |
| 07 | root `foo/**` | `foo`, `foo/x`, `foo/sub/y` | |
| 08 | root `*.log`, `!keep.log` | `a.log`, `keep.log`, `sub/keep.log` | |
| 09 | root `secret/`, `!secret/keep.txt` | `secret/keep.txt`, `secret/o.txt` | |
| 10 | root `secret/*`, `!secret/keep.txt` | as 09 | |
| 11 | `sub/.gitignore` `*.tmp` | `x.tmp`, `sub/x.tmp`, `sub/deep/x.tmp` | |
| 12 | `sub/.gitignore` `/only` | `only`, `sub/only`, `sub/deep/only` | |
| 13 | root `*.log`; `sub/.gitignore` `!keep.log` | `keep.log`, `sub/keep.log`, `sub/x.log` | |
| 14 | root `*.txt`, `!x.txt`; `sub/.gitignore` `x.txt` | `x.txt`, `sub/x.txt` | |
| 15 | root `build/`; `build/.gitignore` `!*` | `build/a` | |
| 16 | `sub/.gitignore` `gen/out` | `sub/gen/out/f`, `gen/out/f` | |
| 17 | `.git/info/exclude` `*.bak` | `a.bak` | |
| 18 | global `*.orig` | `a.orig` | `global_excludes`; `known_diff={"a.orig"}` |
| 19 | `.git/info/exclude` `*.bak`; root `!keep.bak` | `keep.bak`, `x.bak` | |
| 20 | root `# c`, `\#hash`, `\!bang`, `trail.txt   ` | `#hash`, `!bang`, `trail.txt`, `# c` | trailing spaces kept |
| 21 | root `file[0-9].txt`, `f?o` | `file1.txt`, `filea.txt`, `foo`, `fooo` | |
| 22 | root `*.ENV`, `Secret/` | `a.env`, `secret/k` | OS-dependent |
| 23 | root `logs/`, `*.log`, `out/` | `logs/new.txt`, `new.log`, `out`, `new/x.txt` | `create_files=False`; `known_diff={"out"}` |
| 24 | root `node_modules` | `node_modules/p/i.js`, `sub/node_modules/x` | |
| 25 | root `*`, `!*/`, `!*.py` | `a.py`, `a.txt`, `src/b.py`, `src/c.txt`, `.gitignore` | |

Known differences are asserted, not skipped: 18 (global excludes not applied) and 23's `out`
(a non-existent `out` is treated as a directory and refused).

## Case 26 tests

- **Worktree:** set `GIT_AUTHOR_NAME/EMAIL`, `GIT_COMMITTER_NAME/EMAIL` via `monkeypatch`;
  `repo = Repo.init(tmp_path / "main")`; `repo.git.commit("--allow-empty", "-m", "init")`;
  `repo.git.worktree("add", str(tmp_path / "wt"))`; write `main/.git/info/exclude` = `*.bak`;
  create `wt/a.bak`. Assert `"a.bak" in _git_ignored(wt, ["a.bak"])`,
  `is_path_gitignored("a.bak", wt)`, and `"a.bak" not in list_files(".", wt)`.
- **Submodule:** `Repo.init(outer)`; `(outer / ".git" / "modules").mkdir()`;
  `Repo(outer).git.init(f"--separate-git-dir={outer / '.git' / 'modules' / 'sub'}", "sub")`
  (`Repo.init(separate_git_dir=...)` raises `UnsafeOptionError`). If `relative`:
  `(sub / ".git").unlink()` (hidden on Windows) and write `gitdir: ../.git/modules/sub\n`.
  Write `outer/.git/modules/sub/info/exclude` = `*.bak` (create `info/` if missing); create
  `sub/a.bak`. `project_dir` and the `check-ignore` directory are `sub`. Same three assertions.

## Commit

`test(file_tools): check gitignore rules against git check-ignore (#392)`
