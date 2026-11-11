"""Conformance test: gitignore decisions match ``git check-ignore``.

Each scenario builds a repository, asks git which query paths it ignores, and
checks that ``is_path_gitignored`` and ``list_files`` agree. Git is the oracle;
the only allowed differences are listed per scenario in ``known_diff``.
"""

import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from git import Repo

from mcp_workspace.file_tools.directory_utils import is_path_gitignored, list_files

pytestmark = pytest.mark.git_integration


@dataclass(frozen=True)
class Scenario:
    """Rule files to write and paths to ask about."""

    rules: dict[str, str]
    queries: tuple[str, ...]
    create_files: bool = True
    known_diff: frozenset[str] = frozenset()
    global_excludes: str = ""


SCENARIOS: dict[str, Scenario] = {
    "01": Scenario({".gitignore": "*.env\n"}, ("a.env", "sub/a.env", "sub/ok.txt")),
    "02": Scenario(
        {".gitignore": "secret/\n"}, ("secret", "secret/key.txt", "other/secret")
    ),
    "03": Scenario({".gitignore": "/build\n"}, ("build/x", "sub/build/x")),
    "04": Scenario({".gitignore": "docs/tmp\n"}, ("docs/tmp/x", "sub/docs/tmp/x")),
    "05": Scenario({".gitignore": "**/logs\n"}, ("logs/a", "x/y/logs/a")),
    "06": Scenario({".gitignore": "a/**/b\n"}, ("a/b/f", "a/x/y/b/f", "x/a/b/f")),
    "07": Scenario({".gitignore": "foo/**\n"}, ("foo", "foo/x", "foo/sub/y")),
    "08": Scenario(
        {".gitignore": "*.log\n!keep.log\n"}, ("a.log", "keep.log", "sub/keep.log")
    ),
    "09": Scenario(
        {".gitignore": "secret/\n!secret/keep.txt\n"},
        ("secret/keep.txt", "secret/o.txt"),
    ),
    "10": Scenario(
        {".gitignore": "secret/*\n!secret/keep.txt\n"},
        ("secret/keep.txt", "secret/o.txt"),
    ),
    "11": Scenario(
        {"sub/.gitignore": "*.tmp\n"}, ("x.tmp", "sub/x.tmp", "sub/deep/x.tmp")
    ),
    "12": Scenario(
        {"sub/.gitignore": "/only\n"}, ("only", "sub/only", "sub/deep/only")
    ),
    "13": Scenario(
        {".gitignore": "*.log\n", "sub/.gitignore": "!keep.log\n"},
        ("keep.log", "sub/keep.log", "sub/x.log"),
    ),
    "14": Scenario(
        {".gitignore": "*.txt\n!x.txt\n", "sub/.gitignore": "x.txt\n"},
        ("x.txt", "sub/x.txt"),
    ),
    "15": Scenario(
        {".gitignore": "build/\n", "build/.gitignore": "!*\n"}, ("build/a",)
    ),
    "16": Scenario({"sub/.gitignore": "gen/out\n"}, ("sub/gen/out/f", "gen/out/f")),
    "17": Scenario({".git/info/exclude": "*.bak\n"}, ("a.bak",)),
    "18": Scenario(
        {}, ("a.orig",), known_diff=frozenset({"a.orig"}), global_excludes="*.orig\n"
    ),
    "19": Scenario(
        {".git/info/exclude": "*.bak\n", ".gitignore": "!keep.bak\n"},
        ("keep.bak", "x.bak"),
    ),
    "20": Scenario(
        {".gitignore": "# c\n\\#hash\n\\!bang\ntrail.txt   \n"},
        ("#hash", "!bang", "trail.txt", "# c"),
    ),
    "21": Scenario(
        {".gitignore": "file[0-9].txt\nf?o\n"},
        ("file1.txt", "filea.txt", "foo", "fooo"),
    ),
    "22": Scenario({".gitignore": "*.ENV\nSecret/\n"}, ("a.env", "secret/k")),
    "23": Scenario(
        {".gitignore": "logs/\n*.log\nout/\n"},
        ("logs/new.txt", "new.log", "out", "new/x.txt"),
        create_files=False,
        known_diff=frozenset({"out"}),
    ),
    "24": Scenario(
        {".gitignore": "node_modules\n"}, ("node_modules/p/i.js", "sub/node_modules/x")
    ),
    "25": Scenario(
        {".gitignore": "*\n!*/\n!*.py\n"},
        ("a.py", "a.txt", "src/b.py", "src/c.txt", ".gitignore"),
    ),
}


@pytest.fixture
def git_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate git from the user's and the system's configuration.

    Returns:
        The empty global config file git reads.
    """
    home = tmp_path / "home"
    home.mkdir()
    git_config = home / "gitconfig"
    git_config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    return git_config


def _write(path: Path, content: str) -> None:
    """Write content with LF line endings, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="")


def _git_ignored(repo_dir: Path, paths: Sequence[str]) -> set[str]:
    """Ask git which of the paths it ignores.

    Returns:
        The subset of paths ``git check-ignore --no-index`` reports.
    """
    # A real file: GitPython needs fileno(), and binary mode keeps \r out
    with tempfile.TemporaryFile() as f:
        f.write(b"\0".join(p.encode("utf-8") for p in paths) + b"\0")
        f.seek(0)
        status, stdout, stderr = Repo(repo_dir).git.check_ignore(
            "--no-index",
            "--stdin",
            "-z",
            istream=f,
            with_extended_output=True,
            with_exceptions=False,
            stdout_as_string=False,
        )
    # 1 means none of the paths is ignored
    assert status <= 1, stderr
    return {p.decode("utf-8") for p in stdout.split(b"\0") if p}


def _build(root: Path, scenario: Scenario, git_config: Path) -> None:
    """Create the repository, its rule files and, optionally, the query paths."""
    Repo.init(root)
    for rule_file, content in scenario.rules.items():
        _write(root / rule_file, content)

    if scenario.create_files:
        for query in scenario.queries:
            is_parent = any(q.startswith(f"{query}/") for q in scenario.queries)
            if is_parent:
                (root / query).mkdir(parents=True, exist_ok=True)
            elif query not in scenario.rules:
                _write(root / query, "x")

    if scenario.global_excludes:
        excludes = git_config.parent / "global_excludes"
        _write(excludes, scenario.global_excludes)
        _write(git_config, f"[core]\n\texcludesFile = {excludes.as_posix()}\n")


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_matches_git(name: str, tmp_path: Path, git_env: Path) -> None:
    """is_path_gitignored and list_files agree with git check-ignore."""
    scenario = SCENARIOS[name]
    root = tmp_path / "repo"
    _build(root, scenario, git_env)

    by_git = _git_ignored(root, scenario.queries)
    listed = set(list_files(".", root))
    for query in scenario.queries:
        expected = (query in by_git) != (query in scenario.known_diff)
        assert is_path_gitignored(query, root) is expected, query
        if (root / query).is_file():
            assert (query not in listed) is expected, query


def _assert_ignored(project_dir: Path, path: str) -> None:
    """Git, is_path_gitignored and list_files all ignore path."""
    assert path in _git_ignored(project_dir, [path])
    assert is_path_gitignored(path, project_dir)
    assert path not in list_files(".", project_dir)


def test_worktree_info_exclude(
    tmp_path: Path, git_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A linked worktree uses the info/exclude of the main repository."""
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")
    main = tmp_path / "main"
    worktree = tmp_path / "wt"
    repo = Repo.init(main)
    repo.git.commit("--allow-empty", "-m", "init")
    repo.git.worktree("add", str(worktree))
    _write(main / ".git" / "info" / "exclude", "*.bak\n")
    _write(worktree / "a.bak", "x")

    _assert_ignored(worktree, "a.bak")


@pytest.mark.parametrize("relative", [False, True])
def test_submodule_info_exclude(tmp_path: Path, git_env: Path, relative: bool) -> None:
    """A submodule uses the info/exclude under the outer repository's modules/."""
    outer = tmp_path / "outer"
    sub = outer / "sub"
    Repo.init(outer)
    modules = outer / ".git" / "modules"
    modules.mkdir()
    # Repo.init(separate_git_dir=...) raises UnsafeOptionError
    Repo(outer).git.init(f"--separate-git-dir={modules / 'sub'}", "sub")
    if relative:
        # The .git file is hidden on Windows, so it can't be opened for writing
        (sub / ".git").unlink()
        _write(sub / ".git", "gitdir: ../.git/modules/sub\n")
    _write(modules / "sub" / "info" / "exclude", "*.bak\n")
    _write(sub / "a.bak", "x")

    _assert_ignored(sub, "a.bak")
