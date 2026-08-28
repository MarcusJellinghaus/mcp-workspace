# Summary — GitHub read tools: support reference projects for cross-repo reads

Issue: [#255](https://github.com/MarcusJellinghaus/mcp-workspace/issues/255)

## Goal

Add an optional `reference_name` argument to the four GitHub read tools so they can read
issues, PRs and search results from a **reference project** instead of the workspace repo:

```python
github_issue_view(number, ..., reference_name: Optional[str] = None)
github_issue_list(..., reference_name: Optional[str] = None)
github_pr_view(number, ..., reference_name: Optional[str] = None)
github_search(query, ..., reference_name: Optional[str] = None)
```

When omitted, behaviour is byte-for-byte unchanged. When set, the repository is resolved from
the reference-project allowlist that `get_reference_projects()` exposes. Arbitrary
`owner/repo` strings are **not** supported — an unknown name is an error, exactly as it is for
`read_reference_file`.

## Architectural / design changes

### 1. Resolve via the configured URL, never the local path

The tools use `ReferenceProject.url` with `IssueManager(repo_url=...)`. They do **not** route
through `get_reference_project_path()`, because that calls `ensure_available()`, which clones
the entire sibling repo when the directory is missing (`reference_projects.py:101`;
`main.py:147` deliberately allows a URL-only reference project). A GitHub read needs no
working tree, so cloning to read one issue is exactly what this design avoids.

A URL-with-path-fallback design was considered and rejected as dead code: `ReferenceProject.url`
is `None` only when there is no explicit URL *and* the path is not a git repo or has no
`origin` remote, and in that same situation the path route also fails
(`"Directory is not a git repository"` at construction, or `"Could not detect repository from
git remote"` at `_repo_identifier`). The fallback branch could never succeed where the URL
route fails.

**Consequence:** a dict lookup needs no `await`, so all four tools stay synchronous (`def`).
No `asyncio.to_thread` extraction of the kind `git()` needs.

### 2. New synchronous accessor in the protocol layer

`server_reference_tools.py` gains one function:

```python
def get_reference_repo_url(name: str) -> str
```

Synchronous, no `ensure_available()`, no clone. It raises `ValueError` for both failure modes
(unknown name; reference project configured without a URL), keeping a single error site rather
than an accessor plus a `None` check at the call site. This is the "something like
`get_reference_project()`" accessor the issue calls for; the load-bearing part of that
constraint — synchronous, no clone — is preserved.

### 3. Errors are returned as strings, not raised

An unknown `reference_name`, or one without a URL, comes back as `"Error: ..."` — the contract
these four tools already use for every other failure. This diverges from `read_reference_file`
and `git(reference_name=...)`, which raise `ValueError`, and the divergence is deliberate: a
caller of `github_issue_view` already has to inspect the return value, so one extra exception
path for one argument would make the tool harder to use, not safer.

No new error handling is written: a private `_issue_manager()` helper raises, and the existing
`except Exception as e: return f"Error: {e}"` in each tool converts it.

### 4. No host classification — a better error message instead

No denylist of non-GitHub hosts is added. GHES and GHE Cloud are legitimately supported
(`hostname_to_api_base_url` has explicit branches for both), so "not github.com" is not a valid
rejection rule. Instead the two `"Could not access repository"` messages gain the resolved API
base URL, so a GitLab remote surfaces as
`"Error: Could not access repository (tried https://gitlab.com/api/v3)"`. This also helps
diagnose genuine GHES misconfiguration.

**GHE/GHES support does not regress:** the configured URL is passed through verbatim to
`RepoIdentifier.from_repo_url`, which already handles HTTPS and SSH on any hostname. No code on
that path is touched.

### 5. What does *not* change

| Concern | Why no change |
|---|---|
| Manager layer | `BaseGitHubManager.__init__` already accepts exactly one of `project_dir` / `repo_url`. Only the four construction sites move. |
| Issue cache | `_get_cache_file_path()` keys on `RepoIdentifier.cache_safe_name` (`hostname_owner_repo`), so a cross-repo read cannot collide with the workspace cache. |
| `github_search` scoping | It derives `repo:{repo.full_name}` from `manager._get_repository()`, which works identically in `repo_url` mode. |
| Layering | No new module. `server.py` already imports `server_reference_tools`; no `tach.toml` / `.importlinter` edits. |
| Startup performance | `IssueManager` stays behind a function-body import in `_issue_manager()`; the only new module-level import is under `TYPE_CHECKING`, which does not execute. `tests/test_startup_performance.py` is unaffected. |
| Dead-code checks | Both new functions are called from shipped code, so no `vulture_whitelist.py` entry is needed. |

Net effect on `server.py`: the helper **removes** the four per-tool `from ... import
IssueManager` lines it replaces, so the feature lands roughly diff-neutral.

### 6. Out of scope

`check_branch_status`, `get_base_branch`, and the PR-feedback / CI-results paths under
`github_operations/` stay workspace-bound. They are branch- and workflow-oriented — they answer
"is *my* branch ready to merge", which has no cross-repo meaning.

Writes are also out of scope: there are no MCP write tools for GitHub, so appending to or
updating a sibling issue still requires `gh`. This closes the read half only.

## Steps

| Step | Content | Files touched |
|---|---|---|
| [step_1.md](./step_1.md) | Accessor + `_issue_manager()` helper + `reference_name` on the four tools | `server_reference_tools.py`, `server.py`, `test_github_read_tools.py` |
| [step_2.md](./step_2.md) | API base URL in the two `"Could not access repository"` messages | `server.py`, `test_github_read_tools.py` |
| [step_3.md](./step_3.md) | The four documentation surfaces | `server_reference_tools.py`, `test_reference_projects_mcp_tools.py`, `README.md`, `.claude/CLAUDE.md`, `tests/LLM_Test.md` |

Each step is one commit: tests plus implementation plus passing checks. Steps 1 and 2 are
independent of each other; step 3 depends on step 1 only for accurate wording.

## Files and modules

**Created:** none in `src/` or `tests/` — no new module, no new folder.

**Modified:**

| Path | Step | Change |
|---|---|---|
| `src/mcp_workspace/server_reference_tools.py` | 1, 3 | New `get_reference_repo_url()`; `usage` string in `get_reference_projects()` |
| `src/mcp_workspace/server.py` | 1, 2 | New `_issue_manager()`; `reference_name` on four tools; two error messages |
| `tests/github_operations/test_github_read_tools.py` | 1, 2 | Reference-project fixture and tests; two error-message assertions |
| `tests/test_reference_projects_mcp_tools.py` | 3 | Two exact-match `usage` string assertions |
| `README.md` | 3 | Reference-project tool surface |
| `.claude/CLAUDE.md` | 3 | Sibling-repo line (currently an undercount) |
| `tests/LLM_Test.md` | 3 | Manual smoke-test script |

**Untouched deliberately:** `github_operations/` (all of it), `reference_projects.py`,
`tach.toml`, `.importlinter`, `vulture_whitelist.py`, `pr_info/TASK_TRACKER.md` (populated by
`prepare_task_tracker`).

## Open question

`.claude/skills/issue_approve/SKILL.md:29` states that `github_issue_view` "only reaches the
current repository" and routes cross-repo reads to `gh issue view`. That becomes inaccurate
after step 1, but it is outside the four documentation surfaces the issue names. Left alone;
flag if it should be folded into step 3.

## Verification

After every step:

```
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check   (extra_args: ["-n", "auto"] plus the marker exclusions)
mcp__mcp-tools-py__run_mypy_check
```

Then `mcp__mcp-tools-py__run_format_code` before committing.
