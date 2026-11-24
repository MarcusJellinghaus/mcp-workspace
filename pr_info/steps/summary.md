# Summary — #416 Speed up the test suite: GitPython GC, git process count, missing markers

## Goal

Cut Windows test-suite time and make test group markers truthful. Root causes (measured in the issue):

1. GitPython runs `gc.collect()` twice per `Repo.close()` on Windows (and again in `Repo.__del__`) → every `Repo` object is expensive.
2. Each git process costs ~125–380 ms on Windows → test time ≈ number of git processes.

Shared fixtures create a real git repo only to satisfy a GitHub manager constructor. That makes ~145 pure-mock tests start git, and they carry `git_integration` only because of it.

## Scope of this plan

Tasks 0–4 of the issue (automated implementation). Task 5 (baseline/final measurement, counter run, `git_slow_integration` decision, report comment) is **interactive** per decision 9 and is not a step here.

**This change is test-only, plus one config line.** No `src/` code changes.

## Architectural / design changes

| Area | Before | After |
|---|---|---|
| GitHub manager test fixtures | `git.Repo.init` + `create_remote` in `tmp_path`, `PullRequestManager(git_dir)` / `IssueManager(git_dir)`, `get_github_token` patched | Manager built in **repo_url mode**: `Manager(repo_url="https://github.com/<owner>/<repo>.git", github_token="test-token")`. No repo, no token patch, no git process |
| Issue manager fixtures | Two near-identical builders: `mock_issue_manager` (conftest fixture) and `real_issue_manager` (`@contextmanager` helper) | One plain builder `make_issue_manager()` in `tests/github_operations/_issue_test_helpers.py`. `mock_issue_manager` returns it. The two former `real_issue_manager` callers call it directly. `real_issue_manager` is removed |
| No-op patches | `base_manager.Github` / `github.Github` patches in issue fixtures | Removed (they never took effect; the client is built in `_client.build_github_client`). `_client.Github` patches in PR fixtures are kept |
| Git helpers in tests | Helpers open a new `Repo(path)` per call just to run `repo.git.<cmd>` | Helpers run `git.Git(path).<cmd>(...)` / `git.Git(path).execute([...])`: same git process, no `Repo` object, no `gc.collect()` |
| Bulk branch creation | 119 `update_ref` + `push --all` (130 git processes) | One `git push` with 120 refspecs |
| Marker semantics | Markers partly reflect history | Decision 1: **unmarked ⇒ starts no git** (per test). **Marked ⇒ starts git** (per scope: function, class or module). At most one group marker per test (decision 2) |
| mcp-tools-py config | default pytest timeout (300 s) | `pytest-timeout = 2400` in `[tool.mcp-tools-py]` |

### Marker scope rule (used in steps 2, 3, 6)

Pick the scope that is correct with the fewest edits:
- every test in the module starts git → module `pytestmark = pytest.mark.git_integration`
- every test in the class starts git → class decorator
- otherwise → per-test `@pytest.mark.git_integration` (no moving tests between classes)

A scope where no test starts git loses the marker.

### How to tell by reading that a test starts git

It starts git if it (directly or via fixtures) does any of these:
- uses a repo-creating fixture: `git_repo`, `git_repo_with_remote`, `git_repo_with_commit`, `crlf_repo`, `make_conflict_repo` (`tests/git_operations/conftest.py`), `_origin_remote`, `make_clone`, `origin_clone`, `github_test_setup` (`tests/conftest.py`)
- calls `git.Repo.init` / `Repo.clone_from` / `repo.git.<cmd>` / `git.Git(...)`
- calls `subprocess` with `git`
- calls `src` code that runs git and isn't mocked

Merely constructing `Repo(path)` on an existing repo, or reading `.active_branch` / `.head`, does not start git.

## Test-running rules for this issue (override CLAUDE.md)

- Run `run_pytest_check` **only on the test files the step changes**, as paths in `extra_args` (plus `"-n", "auto"`). For a changed shared fixture, run the files that use it. No full-suite or full-group runs.
- Marker-only edits: `--collect-only` on the changed files (`--strict-markers` is in `addopts`).
- `-n 0` only for serial checks or profiling of single files.
- After steps 2, 3 and 5: also `run_ruff_check` and `run_vulture_check` (unused `import git`, helpers, parameters).
- Every step: `run_pylint_check`, `run_mypy_check`, then `run_format_code` before the commit.

## TDD note

Every step only changes test infrastructure, so "test first" means: **the existing tests are the specification** and must pass unchanged in what they assert. No step weakens or deletes an assertion. No test is removed without its coverage moving elsewhere.

## Files created / modified

### Created
- none (except transient `.scratch/` files if profiling in step 5; deleted before commit)

### Modified
| Step | File |
|---|---|
| 1 | `pyproject.toml` |
| 2 | `tests/github_operations/_issue_test_helpers.py` |
| 2 | `tests/github_operations/conftest.py` |
| 2 | `tests/test_server_get_base_branch.py` |
| 2 | `tests/checks/test_branch_status_base_branch.py` |
| 2 | `tests/github_operations/issues/test_comments_mixin.py`, `test_events_mixin.py`, `test_labels_mixin.py`, `test_manager.py`, `test_manager_edit_issue.py`, `test_sub_issues_mixin.py` (markers) |
| 2 | `tests/github_operations/test_github_write_tools_subissues.py` (marker) |
| 3 | `tests/github_operations/test_pr_manager_merged_by_sha.py`, `test_pr_merge_mixin.py`, `test_pr_manager_update_pull_request.py`, `test_pr_checks_mixin.py`, `test_pr_feedback_mixin.py`, `test_pr_feedback_mixin_closing_issues.py` |
| 4 | `tests/git_operations/test_remote_queries.py` |
| 5 | `tests/git_operations/test_ref_snapshot.py` and other test helper modules that open `Repo(path)` only to run `repo.git.<cmd>` (candidate list in step 5) |
| 6 | Unit-group test modules that start git (list in step 6) |

## Steps

1. `step_1.md`: task 0, `pytest-timeout = 2400`
2. `step_2.md`: task 1a, issue manager fixtures in repo_url mode, plus their markers
3. `step_3.md`: task 1b, PR manager fixtures in repo_url mode, plus their markers
4. `step_4.md`: task 2, single push of 120 refspecs
5. `step_5.md`: task 3, fewer `Repo` objects in test helpers (+ decision 4)
6. `step_6.md`: task 4, marker audit of the remaining modules

Each step is exactly one commit.

## Out of scope

- Task 5 (interactive measurement and report)
- Stubbing GitPython's `gc`
- Production `Repo.close()` cost
- Inline `Repo.init` inside individual tests (decision 3)
- Guards (#417)
