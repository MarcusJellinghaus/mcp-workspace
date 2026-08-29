# Issue #232 — Expose GitHub-write MCP tools

## Goal

Expose the GitHub **write** surface as MCP tools: `github_issue_create`,
`github_issue_edit`, `github_issue_comment`, `github_pr_create`,
`github_label_list`. Add the two library functions they need, and one
coarse write-permission probe to `verify_github`.

Today the server exposes GitHub reads only. Every write goes through Bash `gh`,
which needs manual approval interactively and is impossible in the headless
MCP-only flow.

---

## Architectural / design changes

### 1. No new modules, no new architecture boundaries

All five tools live in `server.py`, next to the existing `github_*` read tools.
A separate `server_github_write_tools.py` would need `tach.toml` entries, two
`.importlinter` entries, and a second `_project_dir` setter wired through
`set_project_dir` — cost without benefit. Consequently **`tach.toml`,
`.importlinter` and `.large-files-allowlist` are unchanged**: `server.py` is
already allowlisted, and the new *test* modules are split so none of them
approaches the 750-line limit (see "Test module layout" below).

### 2. Lazy imports stay load-bearing

`tests/test_startup_performance.py` asserts that importing
`mcp_workspace.server` does not pull in `github`/`git`. Every new import of
PyGithub, GitPython, or `github_operations` goes **inside** the tool body, as
the existing read tools do. The module-level helpers therefore annotate their
manager parameter as `Any`, not `IssueManager` — a real annotation would force
a top-level import.

### 3. Write failures must not read as success

`_handle_github_errors` re-raises `ValueError` and 401/403 but swallows 404,
422 and 5xx, returning `default_return`. Each write tool checks the sentinel
explicitly. **The two sentinels differ:**

| Layer | Sentinel |
|---|---|
| `IssueManager` writes | empty `IssueData`, `number == 0` |
| `CommentsMixin.add_comment` | empty `CommentData`, `id == 0` |
| `create_pull_request` | `{}`, so `.get("number")` is `None` |

### 4. `edit_issue` is one combined library function

Not a composition of `close_issue` / `add_labels` / `remove_labels` — those each
do their own fetch → edit → refetch, so one tool call touching state, labels and
title would fire 8+ requests. The new function does: one `_get_issue_checked`
fetch → `issue.edit()` for scalars → server-side additive calls for the
collections → one refetch.

Two consequences the design handles explicitly:

- **`remove_labels` is filtered against the step-1 fetch.** `remove_from_labels`
  is `DELETE .../labels/{name}`, which 404s when the label is absent; the 404 is
  swallowed and the function returns an empty `IssueData`, so a no-op removal
  would report failure *after* the title/body edit already landed.
- **There is no transaction.** On a mid-sequence failure the tool refetches with
  `get_issue` and reports the resulting state behind a warning line, plus
  `Applied:` / `Not applied:` lines derived from that refetch. A caller is never
  told "failed" with no way to learn what landed. Note that failure reaches the
  tool through **two** channels, not one: the empty-`IssueData` sentinel *and* a
  raised exception, because `_handle_github_errors` re-raises 401/403 and every
  `ValueError` — including the `IssueIdentityMismatchError` that the closing
  `_get_issue_checked` throws after all writes have landed. Step 4 routes both
  to the same refetch-and-warn path; a sentinel-only check would return a bare
  error after a successful partial write.

`edit_issue` is also the one place where PyGithub's shapes differ:
`add_to_labels` and `add_to_assignees` are varargs (one request each), but
`remove_from_labels(label)` takes a **single** label, so removals loop.

### 5. Two guards in the tool layer, not the library

- **`status-*` labels are rejected** by `github_issue_create` and
  `github_issue_edit`, on the add *and* remove side. `add_labels(["status-04:…"])`
  can leave an issue with two status labels, a state `set-status` structurally
  prevents; `checks/branch_status.py:351` then returns an arbitrary one. Removing
  a status label leaves zero, which silently falls back to `DEFAULT_LABEL`. The
  error names `mcp-coder gh-tool set-status`.
- **Add-side label names are validated** against `get_available_labels()` before
  writing. Adding an unknown label very likely *creates* it, so a typo
  permanently pollutes the repo's label set — and returning the resulting label
  set does not catch it, because the typo comes back as a real label. The list is
  deliberately **not cached**: the server can run for days and a label created
  meanwhile must not be wrongly rejected. Step 1 first makes
  `get_available_labels()` raise instead of returning `[]` on an API failure —
  otherwise one swallowed 5xx would render as `Error: unknown label(s): bug` and
  block every labelled write while blaming the caller. Validation is skipped
  when the list cannot be read, never inverted.

Both live in one helper, `_check_labels`, which runs the status guard first so a
status label never costs an API call.

### 6. `create_pull_request`'s contract is left alone

It returns `{}` for empty title, bad branch name and unresolvable default
branch, with the reason only logged. Changing that would flip ~8 existing tests
and widen scope. Instead `github_pr_create` pre-validates, reusing
`PullRequestManager._validate_branch_name` so the branch-name rules stay in one
place. `head` defaults to the current branch and `base` to the repository
default — both resolved in the tool so `head != base` is always checkable and
there is one code path rather than two.

### 7. `perm_write` is one coarse boolean, not six synthesised rows

`repo.permissions` is a different mechanism from the six existing probes: one
attribute on the already-fetched repo, no per-permission attribution. Six rows
derived from the same `push` boolean would be five rows of false precision.
The key goes **into `_PROBE_KEYS`** so it inherits the not-accessible
placeholder path and the ordering guarantee, but it gets its own small builder —
`_run_probe` classifies HTTP status, and this is an attribute read.

Note the issue text says `repo.permissions["push"]`; PyGithub's `Permissions` is
an object with a `.push` property, and an unpopulated attribute yields `None`
rather than a bool. The builder tests `is True` / `is False` and maps anything
else to "not checked".

### 8. Return type follows the family

All five return `str` with a machine-readable first line and `f"Error: {e}"` on
failure, matching every existing `github_*` tool. Not structured dicts. The
strings are one to four lines, so they are built inline — no additions to
`formatters.py`.

### 9. Hidden per-client, not server-gated

#233 (server-side tool filter) is on hold; no gate is built. The five tools are
deliberately **not** added to `.claude/settings.local.json`, and their
descriptions state plainly that they mutate GitHub.

---

## Tool contract (shared by all steps)

| Tool | Args | First line |
|---|---|---|
| `github_issue_create` | `title`, `body=""`, `labels=None`, `assignees=None` | `Created issue #42 — <url>` |
| `github_issue_edit` | `number`, `title`, `body`, `add_labels`, `remove_labels`, `add_assignees`, `state` | `Updated issue #42 — <url> (state: open)` |
| `github_issue_comment` | `number`, `body` | `Added comment to issue #42 — <url>` |
| `github_pr_create` | `title`, `body=""`, `head=None`, `base=None` | `Created PR #7 — <url>` |
| `github_label_list` | `search=None` | one line per label: `bug  #d73a4a  Something isn't working` |

`github_issue_edit` follows its first line with:

```
Labels: bug, enhancement
Assignees: alice
```

using `(none)` when a collection is empty. On the partial-write path it prepends

```
Warning: edit partially failed (<reason>) — resulting state below
Applied: title, add_labels
Not applied: add_assignees
```

where `Applied:` / `Not applied:` name only the arguments the caller actually
passed, decided by comparing them against the refetched state.

Every tool body is `@mcp.tool()` + `@log_function_call`, lazy imports inside,
wrapped in `try / except Exception as e: return f"Error: {e}"`.

---

## Files created

| Path | Purpose | Step |
|---|---|---|
| `tests/github_operations/issues/test_manager_edit_issue.py` | Unit tests for the new `edit_issue` | 2 |
| `tests/github_operations/test_github_write_tools_issues.py` | `github_issue_create`, `github_issue_comment`, and the two shared helpers | 3, 5 |
| `tests/github_operations/test_github_write_tools_issue_edit.py` | `github_issue_edit` | 4 |
| `tests/github_operations/test_github_write_tools_labels_pr.py` | `github_label_list`, `github_pr_create` | 6, 7 |

`test_manager.py` is ~600 lines, so `edit_issue` coverage gets its own file
rather than pushing it against the 750-line limit.

### Test module layout — why three files, not one

The five tools carry **~55 mocked tests** between them (12 + 17 + 5 + 9 + 12).
At the ~15 lines a mocked tool test costs in the existing
`test_github_read_tools_issues.py` — decorator, signature, docstring, mock
setup, call, asserts — one combined module lands near **850 lines**, over the
750-line limit and into `.large-files-allowlist` territory for a file that has
no reason to be large. Splitting is the cheaper option, and it splits cleanly
because `github_issue_edit` alone accounts for a third of the tests:

| Module | Tools | Tests | ~lines |
|---|---|---|---|
| `..._issues.py` | create, comment | 17 | ~300 |
| `..._issue_edit.py` | edit | 17 | ~300 |
| `..._labels_pr.py` | label_list, pr_create | 21 | ~350 |

This also mirrors the existing read-tool split
(`test_github_read_tools_issues.py` / `test_github_read_tools_pr_search.py`),
which is grouped by subject rather than one file per tool.

Shared setup — the autouse `setup_server` fixture and the autouse
`server_module._login_cache` reset — goes in the existing
`tests/github_operations/conftest.py` (which already provides `project_dir`) so
all three modules pick it up without duplication.

## Files modified

| Path | Change | Step |
|---|---|---|
| `src/mcp_workspace/github_operations/issues/manager.py` | `create_issue` gains `assignees`; new `edit_issue` + `_issue_to_data` | 1, 2 |
| `src/mcp_workspace/github_operations/issues/labels_mixin.py` | `get_available_labels` drops `@_handle_github_errors` so `[]` no longer doubles as a failure signal | 1 |
| `src/mcp_workspace/github_operations/_permission_probes.py` | `perm_write` key, `_probe_write`, docstrings | 8 |
| `src/mcp_workspace/github_operations/verification.py` | probe section comment says "6" | 8 |
| `src/mcp_workspace/server.py` | `_check_labels`, `_resolve_assignees`, five tools | 3–7 |
| `vulture_whitelist.py` | one entry per tool | 3–7 |
| `tests/github_operations/issues/test_manager.py` | `create_issue(assignees=…)`, `get_available_labels` failure contract | 1 |
| `tests/github_operations/conftest.py` | autouse `setup_server` and `_login_cache` reset for the write-tool modules | 3 |
| `tests/github_operations/issues/test_manager_integration.py` | `edit_issue` in the existing single-issue workflow | 2 |
| `tests/github_operations/test_permission_probes.py` | `perm_write` coverage, fixture, "six" names | 8 |
| `tests/github_operations/test_verification.py` | "six" names and docstrings | 8 |
| `.claude/CLAUDE.md` | tool table + Bash allowlist | 9 |
| `.claude/skills/issue_create/SKILL.md` | `gh issue create` → `github_issue_create` | 9 |
| `.claude/skills/issue_update/SKILL.md` | `gh issue edit --body-file` + tempfile dance → `github_issue_edit` | 9 |
| `.claude/skills/issue_approve/SKILL.md` | `github_issue_comment` for same-repo; `gh` kept for `--repo` | 9 |
| `tests/LLM_Test.md` | new opt-in Section 4 | 9 |

## Files deliberately NOT modified

- `.claude/settings.local.json` — the local half of "hidden per-client".
- `tach.toml`, `.importlinter`, `.large-files-allowlist` — no new module.
- `docs/ARCHITECTURE.md` — the lazy-import rule already covers the new tools.
- `pr_manager.py` — `create_pull_request`'s contract is unchanged.
- `issues/labels_mixin.py`'s `remove_labels(*labels)` — it passes several labels
  to a single-label PyGithub call and is broken for more than one. Pre-existing,
  out of scope, and one more reason `edit_issue` does not compose it. Only
  `get_available_labels` changes in that module (step 1).

---

## Steps

| # | Scope | Layer |
|---|---|---|
| 1 | `create_issue` gains `assignees`; `get_available_labels` stops swallowing errors | library |
| 2 | `edit_issue` + `_issue_to_data` | library |
| 3 | `github_issue_create` + `_check_labels` + `_resolve_assignees` | tool |
| 4 | `github_issue_edit` | tool |
| 5 | `github_issue_comment` | tool |
| 6 | `github_label_list` | tool |
| 7 | `github_pr_create` | tool |
| 8 | `perm_write` probe | verification |
| 9 | `CLAUDE.md` + three issue skills + `LLM_Test.md` | docs |

Steps 3–7 each add their own `vulture_whitelist.py` entry so every commit is
green on its own.

---

## Manual acceptance check (before merge)

`repo.permissions` may reflect the *user's* repo access rather than the
*token's* grant — a read-only token on a repo you own could report
`push: true`, a false green. Check once with a deliberately read-only token
(`BaseGitHubManager(github_token=…)` accepts one explicitly) and **record the
result in the PR description**. If it reports a false green, drop the probe
rather than ship it misleading.

No CI test for this: the question is a property of GitHub, not of this
codebase, and a permanent test would need a second secret that expires and
then silently skips.

---

## Out of scope

Raw `github_api` passthrough; PR merge; comment editing; issue delete;
releases; label definition CRUD; de-duplicating
`get_labels` / `get_available_labels`; `milestone` and `draft` args; close
reason (`completed` / `not_planned`). Workflow status labels stay with
`mcp-coder gh-tool set-status`.
