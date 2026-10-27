# Step 7 — Public `repo_identifier` property

## LLM prompt
Read `pr_info/steps/summary.md`, then implement this step (`pr_info/steps/step_7.md`)
only. Write the tests first, then the implementation. Run pylint, pytest
(`-n auto`) and mypy; all must pass. Run format_code, then make exactly one commit.

## WHERE
- `src/mcp_workspace/github_operations/base_manager.py` — new property
- `src/mcp_workspace/server.py` (~line 208 in the `@me` resolver, ~line 944)
- `src/mcp_workspace/github_operations/_permission_probes.py` (~line 206)
- `src/mcp_workspace/github_operations/issues/base_branch_trust.py` (~line 104)
- `tests/github_operations/test_base_manager.py`

## WHAT
```python
@property
def repo_identifier(self) -> RepoIdentifier:
    """Repository identifier (read-only, lazy).

    Raises:
        ValueError: In project_dir mode when no repository can be detected
            from the git remote.
    """
    return self._repo_identifier
```

## HOW
- Replace `manager._repo_identifier` with `manager.repo_identifier` in the four
  call sites above.
- `server.py:944`: drop the now-unneeded `# pylint: disable=protected-access`.
- `server.py:205`: keep the disable comment — `_cached_login` and
  `_github_client` are still protected.
- Check `_permission_probes.py` and `base_branch_trust.py` for disable comments
  that become unused; remove only those that cover nothing else.
- Leave `pr_manager.py` and `base_manager.py` internal `_repo_identifier` reads as is.
- Docstring `Attributes:` of `BaseGitHubManager`: mention `repo_identifier`.

## ALGORITHM
None (delegation).

## DATA
Returns the same `RepoIdentifier` instance as `_repo_identifier`.

## Tests (`test_base_manager.py`)
- `repo_url` mode → `manager.repo_identifier.full_name == "owner/repo"` and it
  `is manager._repo_identifier`.
- `project_dir` mode with `git_operations.get_repository_identifier` patched to
  return `None` → `pytest.raises(ValueError)`.
- Property is read-only: assigning raises `AttributeError`.
- Existing server / permission-probe / base-branch-trust tests still pass
  (update mocks that set `_repo_identifier` on a `Mock` manager to set
  `repo_identifier` instead, if any fail).
