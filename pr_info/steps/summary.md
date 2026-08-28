# Summary — Issue #256: Guard issue fetches against transfer redirects

## Problem

`repo.get_issue(N)` can silently return an issue from a **different repository**.

When a GitHub issue is transferred to another repository, GitHub answers the old
API URL with a `301`. PyGithub follows it unconditionally inside
`Requester.__requestRaw` — there is no opt-out flag (`follow_302_redirect` gates
`302` only). That behaviour exists to make repository *renames* transparent and
does not distinguish rename from transfer.

The defect in our code is that **nothing validates response identity against
request identity**. `manager.py:150` asks repo X for issue N and copies fields
off whatever comes back.

Two things keep the failure silent:

- `IssueData` has no repository field, so no caller *could* check.
- The only guard, `if not issue["number"]` (`server.py:610`), is a **liveness**
  check. A transferred issue is neither empty nor missing, so liveness passes.

Reads produce convincing, internally consistent output for the wrong issue.
Writes are worse: `add_comment(72, ...)` posts into another repository, and
`set_labels(72, ...)` relabels it — both reachable from
`mcp-coder gh-tool set-status`.

## Approach

Add `BaseGitHubManager._get_issue_checked(repo, issue_number)` and route every
direct `repo.get_issue(` in the issue modules through it. On mismatch, raise
`IssueIdentityMismatchError(ValueError)`.

Two comparisons, both free — no extra API call, both fields already in the
fetched payload:

1. the trailing `owner/repo` of `issue.repository_url` vs `repo.full_name`,
   case-insensitive
2. `issue.number` vs the requested number

Each branch raises the same class with its own message.

## Architectural / design changes

### 1. A new validated-fetch chokepoint on the base manager

`BaseGitHubManager` gains one protected method. This is the only structural
change to production code; everything else is call-site routing.

The method lives on the base manager rather than in `issues/` because the
mixins (`LabelsMixin`, `CommentsMixin`, `EventsMixin`) already annotate
`self: "BaseGitHubManager"`, so they reach it with no new imports and no
inheritance change. `PullRequestManager` inherits it for free, which is what
`_pr_feedback_sources.py` needs.

Resulting invariant: **no bare `repo.get_issue(` in the issue modules.** The one
exception is `server.py:717`, which runs only after `get_pull(number)` already
succeeded and is therefore same-repo by construction.

### 2. A new public exception type in the `github_operations` API surface

`IssueIdentityMismatchError` is defined in `base_manager.py` next to the helper
that raises it, and exported from `github_operations/__init__.py`.

It **must** subclass `ValueError`: `_handle_github_errors` (`base_manager.py:63`)
re-raises only `ValueError`. Anything else it converts to the default return —
empty `IssueData` — and `server.py:610` then degrades the message to a bare
`"Error: Issue #72 not found"`, discarding the transfer target.

The `# Issue-related imports REMOVED per Decision #1` comment in that
`__init__.py` does not apply: the class is raised by `base_manager`, carries no
issue types, and defining it under `issues/` would invert the dependency
(`base_manager` imports nothing from `issues`).

### 3. Error propagation, not sentinel returns

The exception propagates through the existing decorator stack untouched:

- `transition_issue_label` needs **no code change** — it is decorated
  `@_handle_github_errors(default_return=False)` and that decorator re-raises
  `ValueError`. Its `bool` contract is not preserved, by design.
- Existing readers already degrade safely: `checks/branch_status.py:510`,
  `git_operations/base_branch.py:73` and `issues/cache.py:334` all catch
  `Exception` and fall back to "no issue data".
- No new tracebacks reach users: `workflow_utils/label_transitions.py:159`
  already catches `Exception`, and `execute_set_status` has its own handler.

### 4. Message ownership: the exception carries facts, callers own framing

The message text is **client-facing and carries no `Error: ` prefix**. Every
GitHub tool ends `except Exception as e: return f"Error: {e}"` (`server.py` 614,
654, 731, 809), so a prefixed message would render as `Error: Error: …`.

The exception has **no structured attributes** — an empty class body. All three
consumers use `str(e)` only, and `vulture` (a configured dev tool) would flag
unused fields. The transfer target is named in the message, which is where every
consumer reads it from.

### 5. Anchor on `repo.full_name`, never `_repo_identifier.full_name`

The identifier is derived from the git remote (`base_manager.py:283`). Because
PyGithub also follows the *rename* redirect, a stale remote would compare against
the old name and raise a false "transferred". Anchoring on the resolved
`Repository` separates the two cases with no special-casing:

- **Rename** — `get_repo("owner/old")` 301s to `owner/new`; the `Repository`
  stores the new URL, so `repo.get_issue(n)` hits it directly and
  `repository_url` matches. No false positive.
- **Transfer** — `repo.full_name` is `…/mcp_coder`, `issue.repository_url` is
  `…/mcp-workspace`. Fires.

### 6. Visible warning placed in `checks/`, not `git_operations/`

`git_operations` sits *below* `github_operations` in the import-linter layer
stack (see `docs/ARCHITECTURE.md`) and reaches it only via two `ignore_imports`
waivers. Importing the exception into `base_branch.py` would need a third
architectural waiver for a log level. `checks` sits *above* `github_operations`,
so the import is free.

`checks/branch_status.py:510` is also the *outer* of the two catches: when the
fetch raises there, `issue_data` stays `None`, `_detect_from_issue` re-fetches at
`base_branch.py:63` and hits the guard again — warning in both places would log
the same transfer twice per call.

### 7. Test fixtures fixed rather than the guard weakened

`conftest.mock_issue_manager` sets `manager._repository = Mock()`, so
`repo.full_name` is a `Mock` and `repository_url` is set on no mock issue
anywhere. The guard therefore fires in **every existing test that reaches the
helper** (~30 sites). This is fixed in the fixtures, not by teaching the helper
to skip non-`str` values — a check that can quietly stop working is the same
failure class as the bug it fixes.

## Files created / modified

### Created

| Path | Purpose |
|---|---|
| `tests/github_operations/_issue_test_helpers.py` | `make_mock_issue()` — mirrors the existing `_pr_test_helpers.py` convention |
| `pr_info/steps/*.md` | This plan |

### Modified — production (`src/mcp_workspace/`)

| Path | Change |
|---|---|
| `github_operations/base_manager.py` | Add `IssueIdentityMismatchError` + `_get_issue_checked()` |
| `github_operations/__init__.py` | Export the exception; add to `__all__` |
| `github_operations/issues/manager.py` | Route lines 150, 321, 325, 371, 375 |
| `github_operations/issues/comments_mixin.py` | Route lines 80, 127, 205, 265 |
| `github_operations/issues/labels_mixin.py` | Route lines 102, 106, 162, 166, 218, 222 |
| `github_operations/issues/events_mixin.py` | Route line 73 |
| `github_operations/issues/branch_manager.py` | Route line 313 |
| `github_operations/_pr_feedback_sources.py` | Route line 134 |
| `checks/branch_status.py` | Import exception; add `logger.warning` catch before line 510 |

**Not modified, deliberately:** `server.py` (both the `:610` liveness check and
the `:717` bare fetch), `git_operations/base_branch.py`, `issues/cache.py`,
`issues/types.py`, `workflow_utils/label_transitions.py`.

### Modified — tests (`tests/`)

| Path | Change |
|---|---|
| `github_operations/conftest.py` | `mock_repo_obj.full_name = "test/repo"` |
| `github_operations/test_base_manager.py` | New `TestGetIssueChecked` class (3 guard cases) |
| `github_operations/test_package_exports.py` | Export assertion |
| `github_operations/issues/test_manager.py` | Convert mock-issue sites |
| `github_operations/issues/test_labels_mixin.py` | Convert mock-issue sites |
| `github_operations/issues/test_comments_mixin.py` | Convert mock-issue sites |
| `github_operations/issues/test_events_mixin.py` | Convert mock-issue sites |
| `github_operations/issues/test_branch_manager_create.py` | Convert sites + `full_name` on local `mock_repo`s |
| `checks/test_branch_status.py` | Warning-emitted test |

### Folders

No new folders in `src/`. No new test folders.

## Step overview

Ordering is constrained: routing the call sites before the fixtures are prepared
would leave the tree red. Each step is independently green.

| Step | Content | Commit shape |
|---|---|---|
| 1 | `IssueIdentityMismatchError` + `_get_issue_checked` + export, with tests | Production + tests; helper not yet used |
| 2 | Test-fixture preparation (`make_mock_issue`, `full_name`, ~30 site conversions) | Tests only; no production change |
| 3 | Route all 18 call sites, with routing tests | Production + tests |
| 4 | `check_branch_status` visible warning, with test | Production + tests |

## Out of scope

- Removing the redundant re-fetches at `manager.py` 325/375 (`Issue.edit()`
  refreshes in place). They are routed here but not removed — separate issue.
  Note `labels_mixin` 106/166/222 are **load-bearing** and must stay: label ops
  only POST/PUT/DELETE to `…/labels` and never touch the issue object.
- Adding a repository field to `IssueData` — validation happens at fetch time.
- `github_pr_view` — GitHub does not transfer pull requests.
- CLI exit-code handling. **Follow-up to file on `mcp_coder` after this lands:**
  catch `IssueIdentityMismatchError` in `execute_set_status`, print the message,
  exit `3` (current mapping is `0` success / `1` error / `2` usage).

## Known blind spot (recorded so it is not re-investigated)

The `get_base_branch` MCP tool reaches `detect_base_branch` without a prior
fetch, so it stays silent and degrades to "unknown".

## Counting note

The issue prose says "18 `repo.get_issue(` sites in `src/`, 17 routed", but its
own call-site table lists 18 routed. A grep confirms **19 total lines**: 18
routed + `server.py:717` excluded. This plan uses the verified numbers.
