"""Credentials embedded in remote URLs never reach tool output, errors or logs."""

from pathlib import Path
from unittest.mock import patch

import pytest
from git import Repo
from git.exc import GitCommandError

from mcp_workspace import server_reference_tools
from mcp_workspace.git_operations.read_operations import git
from mcp_workspace.github_operations.base_manager import BaseGitHubManager
from mcp_workspace.reference_projects import ReferenceProject, verify_url_match
from mcp_workspace.utils.repo_identifier import RepoIdentifier

SECRET = "ghp_secret123"
URL = f"https://user:{SECRET}@github.com/owner/repo.git"


@pytest.fixture
def repo_with_token_remote(tmp_path: Path) -> Path:
    repo = Repo.init(tmp_path)
    repo.create_remote("origin", URL)
    repo.close()
    return tmp_path


def test_ls_remote_get_url_scrubbed(repo_with_token_remote: Path) -> None:
    output = git("ls_remote", repo_with_token_remote, args=["--get-url", "origin"])
    assert SECRET not in output
    assert "github.com/owner/repo" in output


def test_git_error_with_credentials_scrubbed(repo_with_token_remote: Path) -> None:
    error = GitCommandError(
        ["git", "fetch"], 128, stderr=f"fatal: unable to access '{URL}'"
    )
    with patch(
        "mcp_workspace.git_operations.read_operations._run_simple_command",
        side_effect=error,
    ):
        with pytest.raises(ValueError) as exc_info:
            git("fetch", repo_with_token_remote, args=["origin"])
    assert SECRET not in str(exc_info.value)
    assert "unable to access 'https://github.com/owner/repo.git'" in str(exc_info.value)
    assert exc_info.value.__context__ is None
    assert exc_info.value.__cause__ is None


def test_git_error_without_credentials_unchanged(
    repo_with_token_remote: Path,
) -> None:
    error = GitCommandError(["git", "fetch"], 128, stderr="fatal: no network")
    with patch(
        "mcp_workspace.git_operations.read_operations._run_simple_command",
        side_effect=error,
    ):
        with pytest.raises(GitCommandError):
            git("fetch", repo_with_token_remote, args=["origin"])


def test_diff_output_not_scrubbed(tmp_path: Path) -> None:
    repo = Repo.init(tmp_path)
    (tmp_path / "a.txt").write_text("old\n", encoding="utf-8")
    repo.index.add(["a.txt"])
    repo.index.commit("init")
    repo.close()
    (tmp_path / "a.txt").write_text("ssh://git@host/x\n", encoding="utf-8")
    assert "ssh://git@host/x" in git("diff", tmp_path, compact=False)


def test_repo_identifier_error_scrubbed() -> None:
    with pytest.raises(ValueError) as exc_info:
        RepoIdentifier.from_repo_url(f"ftp://user:{SECRET}@host/x")
    assert "ftp://host/x" in str(exc_info.value)
    assert SECRET not in str(exc_info.value)


def test_manager_repo_url_error_scrubbed() -> None:
    with pytest.raises(ValueError) as exc_info:
        BaseGitHubManager(repo_url=f"ftp://user:{SECRET}@host/x")
    assert "Invalid GitHub repository URL: ftp://host/x" in str(exc_info.value)
    assert SECRET not in str(exc_info.value)


def test_url_mismatch_error_scrubbed() -> None:
    with pytest.raises(ValueError) as exc_info:
        verify_url_match(URL, f"https://user:{SECRET}@github.com/o/other", "p")
    assert "URL mismatch" in str(exc_info.value)
    assert SECRET not in str(exc_info.value)


def test_reference_project_repr_scrubbed(tmp_path: Path) -> None:
    project = ReferenceProject(name="p", path=tmp_path, url=URL)
    assert SECRET not in repr(project)
    assert project.url == URL


def test_get_reference_projects_scrubbed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        server_reference_tools,
        "_reference_projects",
        {
            "p": ReferenceProject(name="p", path=tmp_path, url=URL),
            "q": ReferenceProject(name="q", path=tmp_path),
        },
    )
    result = server_reference_tools.get_reference_projects()
    assert SECRET not in str(result)
    assert result["projects"][0]["url"] == "https://github.com/owner/repo.git"
    assert result["projects"][1]["url"] is None
