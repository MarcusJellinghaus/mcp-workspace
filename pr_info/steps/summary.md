# Summary — Issue #272: `reference_name` for the GitHub issue write tools and `github_label_list`

## Goal

`github_issue_create`, `github_issue_edit`, `github_issue_comment` and `github_label_list`
can only ever target the workspace repository. #255 gave the four GitHub *read* tools a
`reference_name` parameter resolved through the reference-project allowlist; #232 added the
write tools without it, and `github_label_list` — a read tool by behaviour — was misfiled
into that write batch.

This change adds `reference_name: Optional[str] = None` to those four tools, resolved
through the same allowlist, so a configured sibling repository can be read for labels and
written to for issues, comments and edits.

Explicitly **not** in scope: `github_pr_create` (see the issue's *Out of scope*) and the
`IssueManager` inside `get_base_branch` (`server.py:1478`), which reads local git config and
therefore stays bound to `_project_dir`.

## Architectural / design changes

**No new module, no new abstraction, no library-layer change.** The whole feature already
exists one call away:

- `_issue_manager(reference_name)` (`server.py:744`) already returns
  `IssueManager(project_dir=_project_dir)` for `None` and
  `IssueManager(repo_url=get_reference_repo_url(name))` otherwise, and already raises
  `ValueError` for an unknown name or a name without a URL.
- `IssueManager.__init__` (`github_operations/issues/manager.py:75-88`) already accepts
  `repo_url`; every write path (`create_issue`, `edit_issue`, `add_comment`,
  `get_available_labels`) goes through `_repo_identifier` / `_get_repository()`, which are
  repo-source-agnostic.

So the core of the change is **four constructor swaps** — `server.py:1163`, `:1242`,
`:1345`, `:1373` — from `IssueManager(project_dir=_project_dir)` to
`_issue_manager(reference_name)`. Each swap also deletes a now-unused local
`IssueManager` lazy import (`:1159-1160`, `:1228`, `:1341-1342`, `:1369-1370`), which
*reduces* the lazy-import surface `docs/ARCHITECTURE.md:75-79` describes.

Three design points are worth recording:

1. **Resolution route.** Always `ReferenceProject.url` via `get_reference_repo_url()`, never
   `get_reference_project_path()` — that calls `ensure_available()` and would clone an entire
   sibling repository to post one comment. A dedicated test asserts `ensure_available` is
   never called (#255 decision 1, unchanged). The tools therefore stay synchronous (`def`,
   not `async def`).

2. **Every message change is one uniform pattern: an existing string plus a conditional
   suffix.** Five messages must name the target repository or change their advice
   cross-repo. Rather than branching message construction, a three-line helper
   `_ref_suffix(reference_name)` returns `""` or `" in reference project '<name>'"` and is
   inserted at `server.py:111` (before the colon, so the label list stays terminal and a
   multi-label message cannot read the project as another label), `:1176`, `:1285` (after
   "not found or not accessible", the one edit-path message that carries no URL) and
   `:1349`; the `status-*` guard appends its own
   clause `" from the '<name>' project's own checkout"`. When `reference_name` is `None`
   every message is byte-identical to today, which is what keeps the existing exact-equality
   assertion (`test_github_write_tools_issues.py:233`) and the five `"set-status" in result`
   assertions green without editing them.

3. **`_check_labels` takes the reference name; it does not take a repo object.** It already
   receives the manager, so label *validation* follows the target repository for free once
   the manager is built from `reference_name`. It only needs the name to compose the two
   messages it owns. Two of the four tools call it (`github_issue_create`,
   `github_issue_edit`); the other two do not.

Deliberately **rejected** simplifications, recorded so they are not re-proposed:

- Deriving the reference-tool enumeration in `server_reference_tools.py` from a shared
  constant. Two production sites three lines apart, and their tests assert the string by
  exact equality on purpose — a generated string would weaken the check for no gain.
- Keying `_login_cache` per repository. The authenticated user is a property of the token,
  not the target repo, so the single `"login"` slot is correct cross-repo.
- Pre-validating assignees. Per #232 a non-assignable login fails silently; cross-repo this
  widens, and the returned assignee list from the closing refetch is the signal.

## Accepted limitations (from the issue, not defects)

- The `status-` prefix guard is blanket: a sibling repo with a legitimate non-workflow
  `status-…` label could never have it applied. Low risk, accepted.
- `mcp-coder gh-tool set-status` operates on the current checkout, so a sibling repo's issue
  cannot be advanced through its status workflow from here — only from that repo's checkout.
  A newly filed issue belongs in `status-01:created` anyway, which is where the sibling
  repo's own `label-new-issues.yml` puts it. Step 5 records this in README's cross-repo
  section, since this file does not survive the PR.
- The `perm_write` startup probe reads `repo.permissions["push"]` on the workspace repo
  only, so a cross-repo write can fail on a permission the probe reported green.
- A wrong-but-valid `reference_name` on `github_issue_edit` with `state="closed"` can close
  an issue in the wrong sibling repo. Recoverable, and narrower than the `gh` route it
  replaces.

## Steps

| Step | Scope | Commit |
|---|---|---|
| [step_1](./step_1.md) | `github_label_list` + new reference test module | 1 |
| [step_2](./step_2.md) | `github_issue_comment` + `_ref_suffix` helper | 1 |
| [step_3](./step_3.md) | `github_issue_create` + `_check_labels(reference_name)` | 1 |
| [step_4](./step_4.md) | `github_issue_edit` | 1 |
| [step_5](./step_5.md) | Tool enumeration, docs, skill, local allowlist | 1 |

Order is deliberate: `github_label_list` first, because without it a caller writing to a
sibling repo hits `Error: unknown label(s): …` with no way to discover what that repo
defines. Steps 2-4 add one tool each; `_ref_suffix` arrives in step 2 with its first user
and `_check_labels`'s new parameter arrives in step 3 with its first user, so no step leaves
an unused parameter behind.

## Files created or modified

**Created**

- `pr_info/steps/summary.md`, `pr_info/steps/step_1.md` … `step_5.md` (this plan)
- `tests/github_operations/test_github_write_tools_reference.py` (step 1, extended in 2-4)

**Modified**

| File | Steps | What |
|---|---|---|
| `src/mcp_workspace/server.py` | 1-4 | `_ref_suffix` helper; `_check_labels` gains `reference_name`; four tools gain the parameter and call `_issue_manager()`; four unused lazy imports removed; four docstrings updated |
| `src/mcp_workspace/server_reference_tools.py` | 5 | Tool enumeration in the `usage` string (`:77-81`) and in `get_reference_projects`'s docstring (`:47-49`) |
| `tests/github_operations/test_github_write_tools_reference.py` | 1-4 | New module, grown one tool per step |
| `tests/test_reference_projects_mcp_tools.py` | 5 | Two exact-equality assertions on the `usage` string (`:51-64`, `:87-96`) |
| `README.md` | 5 | `:35`, `:84`, `:88`, `:149`, `:374`, `:383` (verbatim usage-string quote), the `:454-460` cross-repo section, and `:473` — the `:149`/`:473` security bullets scoped to file access like `:84`/`:88`; `:443` stays as is |
| `.claude/CLAUDE.md` | 5 | Intro line (`:3`, read-only claim scoped to files); "Sibling repos are readable in full…" line; remove two stale Bash allowlist entries |
| `.claude/skills/issue_approve/SKILL.md` | 5 | Reference-project branch uses `github_issue_comment(reference_name=…)`; `gh` fallback retained |
| `.claude/settings.local.json` | 5 | Add `mcp__mcp-workspace__github_label_list` |
| `tests/LLM_Test.md` | 5 | Cross-repo write script in the mutating Section 4 |
| `pr_info/TASK_TRACKER.md` | — | Populated by tooling from `pr_info/steps/` |

**Verified as needing no change** (so it is not reopened as an omission): `vulture_whitelist.py`
(all nine tool names already listed; a *used* parameter is not a vulture finding), `tach.toml`,
`.importlinter`, `.large-files-allowlist` (no module added, `server.py` already allowlisted),
`docs/ARCHITECTURE.md`, `src/mcp_workspace/github_operations/**` (no manager-layer change), and
the tool-mapping table in `.claude/CLAUDE.md` (lists names only; no tool added or renamed).

## Checks for every step

```
mcp__mcp-tools-py__run_pylint_check
mcp__mcp-tools-py__run_pytest_check   extra_args ["-n", "auto", "-m", "not git_integration and not claude_cli_integration and not claude_api_integration and not formatter_integration and not github_integration and not langchain_integration"]
mcp__mcp-tools-py__run_mypy_check
```

All three must pass before the step is committed.
